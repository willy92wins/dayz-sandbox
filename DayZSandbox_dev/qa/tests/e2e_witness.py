"""Testigo comun de los e2e offline de DayZ Studio (F0.3).

Comprueba que la evidencia de una corrida sale de trafico real entre el bridge y procesos peer, y no de filas
fabricadas dentro del proceso del runner (hallazgo de Sol sobre S-perf: escribir en ``ctx._bridge_writer.write``
dejaba 270 eventos y cero ordenes reales con las aserciones en verde).

Uso (el oraculo lo copia con poco cambio)::

    with e2e_witness.Witness() as w:
        rc = m1_gate.main([...])
    problems = w.verify(evidence_dir)
    self.assertEqual(problems, [], problems)

Como funciona. El ``with`` envuelve, a nivel de clase, los ORIGENES legitimos del nucleo y los restaura al salir
(tambien con excepcion; no deja ``__wrapped__``):

* ``QABridge.enqueue``: la orden encolada de verdad (op_id, verb, inst, ttl_ms, issued_ms, digest de args).
* ``QABridge._dispatch``: cada peticion HTTP. Solo cuenta como trafico real si el handler es un
  ``BaseHTTPRequestHandler`` sobre un socket real conectado al puerto del bridge; anota metodo, ruta,
  client_address y peer/inst.
* ``force_deliver``, ``cut`` (emisores del runner), ``_cut_end`` (temporizador) y ``_expire_delivered``
  (expiraciones, desde temporizador, HTTP o los ``wait_*`` del runner): cada uno con su etiqueta.
* ``QABridge._emit``: anota cada fila emitida con la pila de origenes activa en ese hilo. Una fila emitida sin
  origen adecuado es una fabricacion (``emit_outside_origin``).
* ``PartContext._spawn_peers`` (PIDs reales de los ``Popen``) y la limpieza del directorio temporal (instantanea
  de ``<role>_peer.log``, que el nucleo borra al cerrar).

El otro proceso deja su propia traza (``fake_peer.py``): una linea ``[DSBX_WIT] {...}`` al arrancar (``wit_start`` con
su PID) y otra por cada orden recibida (``recv``) y cada resultado enviado (``sent``, escrita ANTES del POST),
con PID, role, inst, op_id y digest sha256 del JSON canonico.

``verify(evidence_dir, min_resolved_ops=1)`` devuelve una lista de problemas (vacia si todo bien). Cada problema es
un ``str`` con el codigo estable (``p.detail`` lleva el contexto):

* ``unwitnessed_row``: fila de ``bridge.jsonl`` que ningun ``_emit`` envuelto emitio (p. ej. escrita en el escritor).
* ``emit_outside_origin``: ``_emit`` sin origen del nucleo (o con uno que no corresponde a ese evento).
* ``enq_without_enqueue``: ``enq`` sin una llamada a ``enqueue`` con los mismos campos.
* ``duplicate_op_id``: el mismo op_id encolado (``enq``) mas de una vez en la evidencia.
* ``deliver_without_enqueue``: ``deliver`` de un op_id que ningun ``enqueue`` creo.
* ``delivery_without_http`` / ``result_without_http``: ``deliver`` / ``result`` que no salio de un GET /poll /
  POST /result servido por socket.
* ``op_not_in_peer_log``: op resuelta que el peer de ese rol no registra como ``recv`` / ``sent``, u op entregada
  sin ``recv`` cuando ese peer volvio a pedir trabajo despues (ya habia procesado la respuesta).
* ``peer_pid_mismatch``: la traza no lleva el PID del ``Popen`` de ese ``PartContext``.
* ``order_digest_mismatch``: el peer recibio unos args distintos de los que el bridge encolo.
* ``result_digest_mismatch``: el resultado enviado por el peer no es el que el bridge recibio.
* ``no_peer_process``: parte sin ningun peer real lanzado (o con el PID del propio runner).
* ``runner_socket_to_bridge``: el proceso del runner abrio una conexion al puerto del bridge (``socket.connect``):
  los peers legitimos son otros procesos y el nucleo nunca se conecta a su propio bridge.
* ``trace_reused``: una misma linea de traza del peer tendria que acreditar varias filas (p. ej. un resultado
  repetido por HTTP): cada ``deliver`` consume un ``recv`` y cada ``result`` un ``sent``.
* ``too_few_ops``: menos de ``min_resolved_ops`` ops resueltas distintas.

Garantiza: toda fila de la evidencia la emitio el bridge desde un origen real, toda orden entregada/resuelta paso
por un socket y esta en la traza de un proceso hijo con el PID lanzado por el ``PartContext``, con los mismos
digests en ambos lados. NO garantiza: un fabricador que imite a los peers por HTTP contra el bridge Y falsifique
a la vez sus trazas (escribir ``[DSBX_WIT]`` con el PID de un hijo real) no se detecta offline; eso lo cubre el gate
en partida con DayZ. Tampoco cubre filas de ``scenario.jsonl`` ni de otros ficheros, ni un ``Popen`` ajeno a
``_spawn_peers``. Una entrega en los ultimos milisegundos de la parte, sin resultado ni poll posterior del peer,
no exige ``recv`` (el peer pudo morir antes de procesar la respuesta); no da resultados, asi que no acredita nada.
Un solo ``Witness`` activo a la vez. El PID de la traza es el de ``Popen`` (sin lanzadores intermedios tipo venv).
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import socket
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import bridge_qa
import f03_common

WIT_PREFIX = "[DSBX_WIT] "


def digest(obj) -> str:
    """Mismo digest que ``fake_peer.wit_digest`` (duplicado a proposito: el testigo no confia en el peer)."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Problem(str):
    """Codigo estable del problema; ``detail`` lleva el contexto."""

    detail: dict

    def __new__(cls, code: str, detail: dict | None = None):
        obj = super().__new__(cls, code)
        obj.detail = dict(detail or {})
        return obj

    @property
    def code(self) -> str:
        return str.__str__(self)

    def __repr__(self) -> str:
        return f"Problem({self.code!r}, {self.detail!r})"


class _Ann:
    __slots__ = ("bridge", "canon", "row", "stack")

    def __init__(self, bridge, canon, row, stack):
        self.bridge = bridge
        self.canon = canon
        self.row = row
        self.stack = stack


class _PartRec:
    def __init__(self, ctx):
        self.ctx = ctx
        self.samples = _resolve(Path(ctx.samples_dir) / "bridge.jsonl")
        self.pids: dict[str, set] = {}
        self.logs: dict[str, str] = {}
        self.snapshotted = False

    def snapshot(self):
        for role, path in dict(getattr(self.ctx, "peer_logs", {}) or {}).items():
            try:
                self.logs[role] = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                self.logs.setdefault(role, "")
        self.snapshotted = True


class _TmpProxy:
    """Sustituye a ``ctx._tmp_dir``: antes de borrar el directorio temporal, copia los logs de los peers."""

    def __init__(self, real, rec):
        self._real = real
        self._rec = rec

    def cleanup(self):
        try:
            self._rec.snapshot()
        finally:
            self._real.cleanup()

    def __getattr__(self, name):
        return getattr(self._real, name)


def _resolve(path: Path) -> str:
    try:
        return str(Path(path).resolve()).lower()
    except OSError:
        return str(Path(path).absolute()).lower()


_ACTIVE = None
_BRIDGE_ATTRS = ("enqueue", "force_deliver", "cut", "_cut_end", "_expire_delivered", "_dispatch", "_emit")
_PART_ATTRS = ("__init__", "_spawn_peers")


class Witness:
    def __init__(self):
        self._tl = threading.local()
        self._annots: list[_Ann] = []
        self._enqueues: list[dict] = []
        self._http: list[dict] = []
        self._recs: list[_PartRec] = []
        self._conns: list[dict] = []
        self._saved: list[tuple[type, str, object, bool]] = []
        self._active = False

    # ------------------------------------------------------------------ instalacion
    def __enter__(self):
        global _ACTIVE
        if _ACTIVE is not None:
            raise RuntimeError("ya hay un Witness activo")
        _ACTIVE = self
        try:
            self._install()
        except BaseException:
            self._uninstall()
            _ACTIVE = None
            raise
        self._active = True
        return self

    def __exit__(self, exc_type, exc, tb):
        global _ACTIVE
        try:
            self._uninstall()
        finally:
            self._active = False
            if _ACTIVE is self:
                _ACTIVE = None
        return False

    def _patch(self, cls, name, fn):
        own = name in cls.__dict__
        self._saved.append((cls, name, cls.__dict__[name] if own else None, own))
        fn.__name__ = name
        setattr(cls, name, fn)

    def _uninstall(self):
        while self._saved:
            cls, name, orig, own = self._saved.pop()
            if own:
                setattr(cls, name, orig)
            else:
                # el atributo era heredado (p. ej. socket.socket.connect, de _socket.socket): se quita el parche.
                try:
                    delattr(cls, name)
                except AttributeError:
                    pass

    def _stack(self) -> list:
        st = getattr(self._tl, "stack", None)
        if st is None:
            st = self._tl.stack = []
        return st

    def _install(self):
        QB = bridge_qa.QABridge
        PC = f03_common.PartContext
        me = self
        o = {n: QB.__dict__[n] for n in _BRIDGE_ATTRS}
        po = {n: PC.__dict__[n] for n in _PART_ATTRS}

        def simple(kind, name):
            orig = o[name]

            def wrapper(bridge, *a, **kw):
                rec = {"kind": kind, "bridge": bridge}
                st = me._stack()
                st.append(rec)
                try:
                    return orig(bridge, *a, **kw)
                finally:
                    st.pop()

            return wrapper

        def enqueue(bridge, peer, verb, args, target_inst, ttl_ms, op_id=None, issued_ms=None):
            rec = {
                "kind": "enqueue",
                "bridge": bridge,
                "peer": peer,
                "verb": verb,
                "inst": target_inst,
                "ttl_ms": ttl_ms,
                "issued_ms": issued_ms,
                "ok": False,
                "op_id": None,
                "args_digest": None,
                "row_args_digest": None,
            }
            try:
                full = bridge_qa.full_args(args)
                rec["args_digest"] = digest(full)
                rec["row_args_digest"] = digest(bridge_qa._strip_qa_fault(full))
            except Exception:
                pass
            st = me._stack()
            st.append(rec)
            try:
                result = o["enqueue"](bridge, peer, verb, args, target_inst, ttl_ms, op_id, issued_ms)
                rec["op_id"] = result
                rec["ok"] = True
                return result
            finally:
                st.pop()
                me._enqueues.append(rec)

        def dispatch(bridge, handler):
            parts = urlsplit(getattr(handler, "path", "") or "")
            query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
            sock = getattr(handler, "request", None)
            real = False
            try:
                real = (
                    isinstance(handler, http.server.BaseHTTPRequestHandler)
                    and isinstance(sock, socket.socket)
                    and sock.getsockname()[1] == bridge.port
                )
            except Exception:
                real = False
            rec = {
                "kind": "http" if real else "http_unsocketed",
                "bridge": bridge,
                "method": getattr(handler, "command", None),
                "path": parts.path,
                "client_address": tuple(getattr(handler, "client_address", ()) or ()),
                "peer": query.get("peer"),
                "inst": query.get("inst"),
            }
            me._http.append(rec)
            st = me._stack()
            st.append(rec)
            try:
                return o["_dispatch"](bridge, handler)
            finally:
                st.pop()

        def emit(bridge, fields):
            before = len(bridge.events)
            try:
                return o["_emit"](bridge, fields)
            finally:
                if len(bridge.events) > before:
                    row = bridge.events[-1]
                    me._annots.append(
                        _Ann(
                            bridge,
                            json.dumps(row, sort_keys=True, ensure_ascii=False),
                            dict(row),
                            list(me._stack()),
                        )
                    )

        def part_init(ctx, *a, **kw):
            po["__init__"](ctx, *a, **kw)
            me._recs.append(_PartRec(ctx))

        def spawn(ctx, *a, **kw):
            result = po["_spawn_peers"](ctx, *a, **kw)
            rec = me._rec_for(ctx)
            if rec is not None:
                for role, proc in ctx.procs.items():
                    rec.pids.setdefault(role, set()).add(proc.pid)
                if ctx._tmp_dir is not None and not isinstance(ctx._tmp_dir, _TmpProxy):
                    ctx._tmp_dir = _TmpProxy(ctx._tmp_dir, rec)
            return result

        # Conexiones de ESTE proceso (el del runner) al puerto de un bridge: los peers legitimos son otros procesos,
        # y el nucleo nunca se conecta a su propio bridge. Una conexion asi es una suplantacion por HTTP.
        sock_cls = socket.socket
        orig_connect = sock_cls.connect
        orig_connect_ex = sock_cls.connect_ex

        def note_conn(address):
            try:
                host, port = address[0], int(address[1])
            except Exception:
                return
            ports = set()
            for rec in me._recs:
                b = getattr(rec.ctx, "bridge", None)
                if b is not None:
                    try:
                        ports.add(int(b.port))
                    except Exception:
                        pass
            if port in ports:
                me._conns.append({"host": host, "port": port, "thread": threading.get_ident()})

        def connect(sock, address):
            note_conn(address)
            return orig_connect(sock, address)

        def connect_ex(sock, address):
            note_conn(address)
            return orig_connect_ex(sock, address)

        self._patch(sock_cls, "connect", connect)
        self._patch(sock_cls, "connect_ex", connect_ex)
        self._patch(QB, "enqueue", enqueue)
        self._patch(QB, "force_deliver", simple("force_deliver", "force_deliver"))
        self._patch(QB, "cut", simple("cut", "cut"))
        self._patch(QB, "_cut_end", simple("cut_end", "_cut_end"))
        self._patch(QB, "_expire_delivered", simple("expire_delivered", "_expire_delivered"))
        self._patch(QB, "_dispatch", dispatch)
        self._patch(QB, "_emit", emit)
        self._patch(PC, "__init__", part_init)
        self._patch(PC, "_spawn_peers", spawn)

    def _rec_for(self, ctx):
        for rec in self._recs:
            if rec.ctx is ctx:
                return rec
        return None

    # ------------------------------------------------------------------ verificacion
    def verify(self, evidence_dir, min_resolved_ops: int = 1, require_peers: bool = True) -> list:
        problems: list[Problem] = []

        def add(code, **detail):
            problems.append(Problem(code, detail))

        files = sorted(Path(evidence_dir).rglob("bridge.jsonl"))
        resolved_set: set = set()
        enq_seen: dict[str, int] = {}
        for fpath in files:
            key = _resolve(fpath)
            recs = [r for r in self._recs if r.samples == key]
            for r in recs:
                if not r.snapshotted:
                    r.snapshot()
            bridges = [r.ctx.bridge for r in recs if r.ctx.bridge is not None]
            bids = {id(b) for b in bridges}
            anns = [a for a in self._annots if id(a.bridge) in bids]
            enqs = [e for e in self._enqueues if id(e["bridge"]) in bids and e["ok"]]
            pool: dict[str, list[_Ann]] = {}
            for a in anns:
                pool.setdefault(a.canon, []).append(a)
            pids: dict[str, set] = {}
            logs: dict[str, list[dict]] = {}
            for r in recs:
                for role, s in r.pids.items():
                    pids.setdefault(role, set()).update(s)
                for role, text in r.logs.items():
                    logs.setdefault(role, []).extend(_parse_trace(text))

            # peers reales
            real_pids = {role: {p for p in s if p != os.getpid()} for role, s in pids.items()}
            if require_peers and not any(real_pids.values()):
                add("no_peer_process", file=str(fpath))
            for role, s in real_pids.items():
                for pid in s:
                    started = [x for x in logs.get(role, []) if x.get("ev") == "wit_start" and x.get("pid") == pid]
                    if not started:
                        add("peer_pid_mismatch", role=role, pid=pid, why="sin linea wit_start de ese PID")

            # el proceso del runner no se conecta nunca al bridge: eso solo lo hacen los peers, desde otro proceso
            ports = set()
            for b in bridges:
                try:
                    ports.add(int(b.port))
                except Exception:
                    pass
            hits = [c for c in self._conns if c["port"] in ports]
            if hits:
                add("runner_socket_to_bridge", file=str(fpath), connections=len(hits))

            # origenes de todo _emit anotado
            for a in anns:
                code = _origin_problem(a)
                if code is not None:
                    add(code, ev=a.row.get("ev"), row=a.row)

            raw_lines = fpath.read_text(encoding="utf-8").splitlines()
            # Una entrega exige su `recv` en la traza del peer si la op se resolvio, o si ese peer volvio a
            # pedir trabajo despues (entonces ya habia procesado la respuesta). Asi una entrega en los ultimos
            # milisegundos antes de cerrar la parte no rechaza una corrida honesta.
            resolved_ids: set = set()
            later_polls: dict = {}
            for line in raw_lines:
                try:
                    pre = json.loads(line) if line.strip() else None
                except ValueError:
                    pre = None
                if not isinstance(pre, dict):
                    continue
                if pre.get("ev") == "result" and pre.get("http") == 200:
                    resolved_ids.add(pre.get("op_id"))
                if pre.get("ev") in ("poll", "keepalive") and isinstance(pre.get("t_ms"), (int, float)):
                    peer = pre.get("peer")
                    later_polls[peer] = max(later_polls.get(peer, float("-inf")), pre["t_ms"])

            def need_recv(row) -> bool:
                if row.get("op_id") in resolved_ids:
                    return True
                t = row.get("t_ms")
                return isinstance(t, (int, float)) and later_polls.get(row.get("peer"), float("-inf")) > t

            # cada linea de traza acredita UNA fila: una entrega consume un `recv` y un resultado consume un `sent`
            used = {"recv": set(), "sent": set()}
            for lineno, line in enumerate(raw_lines, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    add("unwitnessed_row", file=str(fpath), line=lineno, why="json invalido")
                    continue
                canon = json.dumps(row, sort_keys=True, ensure_ascii=False)
                bucket = pool.get(canon)
                if not bucket:
                    add("unwitnessed_row", file=str(fpath), line=lineno, ev=row.get("ev"))
                    continue
                ann = bucket.pop()
                if row.get("ev") == "enq":
                    enq_seen[row.get("op_id")] = enq_seen.get(row.get("op_id"), 0) + 1
                self._check_row(row, ann, enqs, logs, real_pids, add, need_recv, used)
                if row.get("ev") == "result" and row.get("http") == 200:
                    resolved_set.add((key, row.get("op_id")))

        for oid, n in enq_seen.items():
            if n > 1:
                add("duplicate_op_id", op_id=oid, times=n)
        if len(resolved_set) < int(min_resolved_ops):
            add("too_few_ops", resolved=len(resolved_set), minimum=int(min_resolved_ops))
        return problems

    def _check_row(self, row, ann, enqs, logs, real_pids, add, need_recv, used):
        ev = row.get("ev")
        top = ann.stack[-1] if ann.stack else None
        if ev == "enq":
            ok = (
                top is not None
                and top["kind"] == "enqueue"
                and top["op_id"] == row.get("op_id")
                and top["peer"] == row.get("peer")
                and top["verb"] == row.get("verb")
                and top["inst"] == row.get("inst")
                and top["row_args_digest"] == digest(row.get("args"))
            )
            if not ok:
                add("enq_without_enqueue", row=row)
            return
        if ev == "deliver":
            http = _http_in(ann.stack)
            if http is None or http["kind"] != "http" or http["path"] != "/poll" or http["method"] != "GET" or http["peer"] != row.get("peer"):
                add("delivery_without_http", row=row)
            enq = next((e for e in enqs if e["op_id"] == row.get("op_id")), None)
            if enq is None:
                add("deliver_without_enqueue", row=row)
                return
            if need_recv(row):
                self._check_trace(row, "recv", enq["args_digest"], logs, real_pids, add, "order_digest_mismatch", used["recv"])
            return
        if ev == "result" and row.get("http") == 200:
            http = _http_in(ann.stack)
            if http is None or http["kind"] != "http" or http["path"] != "/result" or http["method"] != "POST" or http["peer"] != row.get("peer"):
                add("result_without_http", row=row)
            self._check_trace(row, "recv", None, logs, real_pids, add, None)
            self._check_trace(row, "sent", digest(row.get("result")), logs, real_pids, add, "result_digest_mismatch", used["sent"])

    @staticmethod
    def _check_trace(row, phase, expect_digest, logs, real_pids, add, digest_code, used=None):
        role = row.get("peer")
        op_id = row.get("op_id")
        lines = [x for x in logs.get(role, []) if x.get("ev") == "wit" and x.get("phase") == phase and x.get("op_id") == op_id]
        if not lines:
            add("op_not_in_peer_log", phase=phase, role=role, op_id=op_id)
            return
        mine = [x for x in lines if x.get("pid") in real_pids.get(role, set()) and x.get("role") == role]
        if not mine:
            add("peer_pid_mismatch", phase=phase, role=role, op_id=op_id, pids=sorted({x.get("pid") for x in lines}))
            return
        good = mine if expect_digest is None else [x for x in mine if x.get("digest") == expect_digest]
        if not good:
            add(digest_code, phase=phase, role=role, op_id=op_id)
            return
        if used is not None:
            # una linea de traza solo acredita una fila: un resultado repetido necesita su propio `sent`
            free = [x for x in good if id(x) not in used]
            if not free:
                add("trace_reused", phase=phase, role=role, op_id=op_id, lines=len(good))
                return
            used.add(id(free[0]))


def _parse_trace(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if not line.startswith(WIT_PREFIX):
            continue
        try:
            obj = json.loads(line[len(WIT_PREFIX):])
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _http_in(stack):
    for rec in reversed(stack):
        if rec["kind"] in ("http", "http_unsocketed"):
            return rec
    return None


_RUNNER_ORIGIN = {
    "force": "force_deliver",
    "cut_start": "cut",
    "cut_end": "cut_end",
    "lost": "expire_delivered",
    "enq": "enqueue",
}


def _origin_problem(ann: _Ann):
    """None si la fila salio de un origen del nucleo que le corresponde; si no, el codigo."""
    if not ann.stack:
        return "emit_outside_origin"
    ev = ann.row.get("ev")
    want = _RUNNER_ORIGIN.get(ev)
    top = ann.stack[-1]
    if want is not None:
        return None if top["kind"] == want else "emit_outside_origin"
    http = _http_in(ann.stack)
    if http is None:
        return "emit_outside_origin"
    if http["kind"] == "http_unsocketed":
        # deliver/result se reportan como sin HTTP en _check_row; el resto, como fuera de origen.
        return None if ev in ("deliver", "result") else "emit_outside_origin"
    return None
