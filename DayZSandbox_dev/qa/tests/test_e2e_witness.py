"""Pruebas del testigo comun de los e2e (tests/e2e_witness.py): una honesta (P1) y ocho fabricaciones (N1-N8)."""

import argparse
import http.client
import json
import shutil
import socket
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import bridge_qa
import f03_common
import wire

from . import e2e_witness

FAST = dict(
    both=True,
    build="offline",
    client_profile=None,
    evaluate_only=False,
    fault=None,
    hold_ms=300,
    lease_ms=600,
    peer_timeout=20,
    retry_ms=300,
    seed=20261026,
    server_profile=None,
    ttl_ms=1000,
)


def _args(**extra):
    values = dict(FAST)
    values.update(extra)
    return argparse.Namespace(**values)


def _ctx(base, **extra):
    return f03_common.PartContext(
        base_dir=Path(base),
        part_name="run",
        spike_id="F0.3-0",
        args=_args(**extra),
        argv=[],
    )


def _real_ops(ctx, n=1):
    for peer in ctx.required_peers():
        for _ in range(n):
            out = f03_common.issue_one(ctx, peer, "qa_echo")
            assert out.status == "done", out


def _codes(problems):
    return {p.code for p in problems}


class E2EWitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dsbx-witness-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _verify(self, w, **kw):
        return w.verify(self.tmp, **kw)

    def test_restores_class_and_leaves_no_wrapped(self):
        before = {n: bridge_qa.QABridge.__dict__[n] for n in ("enqueue", "_emit", "_dispatch", "_cut_end")}
        pc_before = f03_common.PartContext.__dict__["_spawn_peers"]
        self.assertNotIn("connect", socket.socket.__dict__)
        with self.assertRaises(ZeroDivisionError):
            with e2e_witness.Witness():
                self.assertIsNot(bridge_qa.QABridge.__dict__["_emit"], before["_emit"])
                self.assertFalse(hasattr(bridge_qa.QABridge.__dict__["_emit"], "__wrapped__"))
                self.assertIn("connect", socket.socket.__dict__)
                1 / 0
        for n, fn in before.items():
            self.assertIs(bridge_qa.QABridge.__dict__[n], fn)
        self.assertIs(f03_common.PartContext.__dict__["_spawn_peers"], pc_before)
        # connect/connect_ex son heredados de _socket.socket: al salir se quita el parche, no se deja otra copia
        self.assertNotIn("connect", socket.socket.__dict__)
        self.assertNotIn("connect_ex", socket.socket.__dict__)

    def test_p1_honest_real_peers_and_orders(self):
        with e2e_witness.Witness() as w:
            with _ctx(self.tmp) as ctx:
                self.assertIsNone(ctx.startup_reason)
                _real_ops(ctx, 2)
        problems = self._verify(w, min_resolved_ops=4)
        self.assertEqual(problems, [], problems)

    def test_n1_rows_written_straight_into_the_writer(self):
        with e2e_witness.Witness() as w:
            with _ctx(self.tmp) as ctx:
                self.assertIsNone(ctx.startup_reason)
                for i in range(30):
                    ctx._bridge_writer.write({"ev": "poll", "http": 200, "peer": "server", "t_ms": 1000.0 + i, "n_ops": 0})
        problems = self._verify(w)
        self.assertIn("unwitnessed_row", _codes(problems), problems)

    def test_n2_runner_calls_emit_itself(self):
        with e2e_witness.Witness() as w:
            with _ctx(self.tmp) as ctx:
                self.assertIsNone(ctx.startup_reason)
                _real_ops(ctx)
                with ctx.bridge.cv:
                    ctx.bridge._emit({"ev": "result", "http": 200, "op_id": "op-fake-1", "peer": "server", "result": {"status": "done"}})
        problems = self._verify(w)
        self.assertIn("emit_outside_origin", _codes(problems), problems)
        self.assertNotIn("unwitnessed_row", _codes(problems), problems)

    def test_n3_no_peer_process_and_fabricated_rows(self):
        with e2e_witness.Witness() as w:
            bridge = bridge_qa.QABridge(hold_ms=300, lease_ms=600, sink=lambda row: None)
            ctx = f03_common.PartContext.from_bridge(bridge, self.tmp / "run")
            writer = f03_common._JsonlWriter(ctx.samples_dir / "bridge.jsonl")
            for i in range(5):
                writer.write({"ev": "result", "http": 200, "op_id": f"op-x-{i}", "peer": "server", "result": {}, "t_ms": float(i)})
            writer.close()
            ctx.close()
            bridge.httpd.server_close()
        problems = self._verify(w)
        self.assertIn("no_peer_process", _codes(problems), problems)
        self.assertIn("unwitnessed_row", _codes(problems), problems)

    def test_n4_half_real_half_fabricated(self):
        with e2e_witness.Witness() as w:
            with _ctx(self.tmp) as ctx:
                self.assertIsNone(ctx.startup_reason)
                _real_ops(ctx)
                for i in range(5):
                    ctx._bridge_writer.write({"ev": "result", "http": 200, "op_id": f"op-x-{i}", "peer": "client", "result": {"status": "done"}, "t_ms": 9000.0 + i})
        problems = self._verify(w)
        self.assertEqual(_codes(problems), {"unwitnessed_row"}, problems)
        self.assertEqual(len(problems), 5, problems)

    def test_n5_runner_impersonates_a_peer_over_http(self):
        with e2e_witness.Witness() as w:
            with _ctx(self.tmp, both=False) as ctx:
                self.assertIsNone(ctx.startup_reason)
                port = ctx.bridge.port
                key = ctx.keys["client"]
                inst = "f" * 32

                def call(method, path, query, body=None):
                    q = urllib.parse.urlencode({"key": key, **query})
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                    raw = None if body is None else json.dumps(body)
                    conn.request(method, f"{path}?{q}", body=raw, headers={"Content-Type": "application/json"})
                    resp = conn.getresponse()
                    data = json.loads(resp.read().decode("utf-8") or "null")
                    conn.close()
                    return resp.status, data

                code, _ = call(
                    "POST",
                    "/hello",
                    {},
                    {"build": "offline", "inst": inst, "peer": "client", "probe_ver": "x", "proto": "qa0"},
                )
                self.assertEqual(code, 200)
                op_id = ctx.bridge.enqueue("client", "qa_echo", wire.empty_payload(), inst, 5000)
                code, polled = call("GET", "/poll", {"peer": "client", "inst": inst, "frame": "1", "tick_s": "0"})
                self.assertEqual((code, [o["op_id"] for o in polled["ops"]]), (200, [op_id]))
                code, _ = call("POST", "/result", {"peer": "client", "inst": inst}, {"op_id": op_id, "status": "done"})
                self.assertEqual(code, 200)
                _real_ops(ctx)  # el peer server si es real
        problems = self._verify(w)
        self.assertIn("op_not_in_peer_log", _codes(problems), problems)
        self.assertIn("runner_socket_to_bridge", _codes(problems), problems)
        self.assertNotIn("unwitnessed_row", _codes(problems), problems)
        self.assertNotIn("emit_outside_origin", _codes(problems), problems)

    def test_n6_result_changes_between_peer_and_bridge(self):
        orig = bridge_qa.QABridge._result

        def tampered(self, handler, query, body, body_len=0):
            if isinstance(body, dict):
                body = dict(body)
                body["tampered"] = 1
            return orig(self, handler, query, body, body_len)

        with mock.patch.object(bridge_qa.QABridge, "_result", tampered):
            with e2e_witness.Witness() as w:
                with _ctx(self.tmp) as ctx:
                    self.assertIsNone(ctx.startup_reason)
                    _real_ops(ctx)
        problems = self._verify(w)
        self.assertIn("result_digest_mismatch", _codes(problems), problems)

    def test_n7_runner_repeats_old_op_ids(self):
        # (a) copia filas de una corrida honesta anterior; (b) vuelve a encolar un op_id ya usado.
        old = self.tmp / "old"
        with e2e_witness.Witness() as w:
            with _ctx(old) as ctx0:
                self.assertIsNone(ctx0.startup_reason)
                _real_ops(ctx0)
            old_rows = [
                json.loads(x) for x in (old / "run" / "samples" / "bridge.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            new = self.tmp / "new"
            with _ctx(new) as ctx:
                self.assertIsNone(ctx.startup_reason)
                _real_ops(ctx)
                for row in old_rows:
                    ctx._bridge_writer.write(row)
                used = next(r["op_id"] for r in old_rows if r.get("ev") == "enq")
                inst = ctx.bridge.registered("server")
                ctx.bridge.enqueue("server", "qa_echo", wire.empty_payload(), inst, 1000, op_id=used)
                ctx.bridge.enqueue("server", "qa_echo", wire.empty_payload(), inst, 1000, op_id=used)
        problems = w.verify(new)
        self.assertIn("unwitnessed_row", _codes(problems), problems)
        self.assertIn("duplicate_op_id", _codes(problems), problems)

    def test_n8_runner_replays_a_real_result_over_http(self):
        # Puntos que Sol dejo apuntados antes del corte del filtro: el origen HTTP solo miraba el puerto local, y
        # una misma linea `sent` de la traza acreditaba varios resultados repetidos.
        with e2e_witness.Witness() as w:
            with _ctx(self.tmp, both=False) as ctx:
                self.assertIsNone(ctx.startup_reason)
                _real_ops(ctx)
                res = next(e for e in ctx.bridge.events if e.get("ev") == "result" and e.get("http") == 200)
                peer = res["peer"]
                q = urllib.parse.urlencode({"key": ctx.keys[peer], "peer": peer, "inst": ctx.bridge.registered(peer)})
                for _ in range(2):
                    conn = http.client.HTTPConnection("127.0.0.1", ctx.bridge.port, timeout=10)
                    conn.request("POST", f"/result?{q}", body=json.dumps(res["result"]), headers={"Content-Type": "application/json"})
                    self.assertEqual(conn.getresponse().status, 200)
                    conn.close()
        problems = self._verify(w)
        self.assertIn("runner_socket_to_bridge", _codes(problems), problems)
        self.assertIn("trace_reused", _codes(problems), problems)
        self.assertNotIn("unwitnessed_row", _codes(problems), problems)


if __name__ == "__main__":
    unittest.main()
