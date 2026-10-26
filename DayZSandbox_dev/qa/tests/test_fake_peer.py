"""Peer falso: orden P5, rafaga sin bloquear el frame y el contador de fallos."""

import socket
import threading
import time
import unittest

from bridge_qa import full_args
from fake_peer import Peer


def _peer():
    peer = Peer("unused", "server", 9, 60, None)
    peer.inst = "aa" * 16
    peer.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return peer


def _op(op_id, inst, issued_ms=0, ttl_ms=5000):
    return {
        "args": full_args({}),
        "inst": inst,
        "issued_ms": issued_ms,
        "op_id": op_id,
        "ttl_ms": ttl_ms,
        "verb": "srv_read",
    }


class FakePeerTests(unittest.TestCase):
    def tearDown(self):
        if getattr(self, "peer", None) is not None:
            self.peer.alive = False
            self.peer.udp.close()

    def test_sol10_repeat_checks_instance_and_ttl_before_cache(self):
        self.peer = _peer()
        bucket = []
        self.peer.cache["again"] = {
            "dup": False,
            "op_id": "again",
            "read": {"has": ["frame"]},
            "reason": "",
            "status": "done",
        }
        self.peer._start_op(_op("again", "zz" * 16), 0, 0, bucket)
        self.assertEqual(bucket[0]["status"], "rejected")
        self.assertEqual(bucket[0]["reason"], "stale_instance")
        bucket.clear()
        self.peer._start_op(_op("again", self.peer.inst, issued_ms=0, ttl_ms=1), 50, 0, bucket)
        self.assertEqual(bucket[0]["reason"], "expired")

    def test_sol10_same_op_twice_in_one_batch_is_a_duplicate(self):
        self.peer = _peer()
        self.peer.frame = 3
        bucket = []
        done = threading.Event()
        op = _op("new", self.peer.inst, issued_ms=0, ttl_ms=5000)
        self.peer.inbox.put(([op, dict(op)], 0, bucket, done))
        self.peer._pump()
        self.peer.frame += 1
        self.peer._pump()
        self.peer.frame += 1
        self.peer._pump()
        self.assertTrue(done.is_set())
        self.assertEqual([row["status"] for row in bucket], ["done", "done"])
        self.assertIs(bucket[0]["dup"], False)
        self.assertIs(bucket[1]["dup"], True)

    def test_sol13_burst_does_not_stall_frames(self):
        self.peer = _peer()
        sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sink.bind(("127.0.0.1", 0))
        self.peer.rpc_port = sink.getsockname()[1]
        self.addCleanup(sink.close)
        thread = threading.Thread(target=self.peer._frame_loop, daemon=True)
        thread.start()
        bucket = []
        done = threading.Event()
        op = _op("burst", self.peer.inst, ttl_ms=60000)
        op["verb"] = "rpc_burst"
        op["args"] = full_args(
            {
                "client_inst": "cc" * 16,
                "count": 40,
                "interval_ms": 300,
                "pos": [7200, 360, 7200],
                "seq0": 1000,
                "ypr": [90, 0, 0],
            }
        )
        self.peer.inbox.put(([op], 0, bucket, done))
        time.sleep(0.2)
        start = self.peer.frame
        time.sleep(1.0)
        rate = self.peer.frame - start
        self.assertGreater(rate, 10)
        self.assertFalse(done.is_set())
        self.peer.alive = False
        thread.join(timeout=2)
