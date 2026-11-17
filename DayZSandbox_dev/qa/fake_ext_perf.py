"""Extension esqueleto de S-perf para fake_peer (prefijo perf_, RPC 26102860..26102869)."""

from fake_peer import FakeExt

PREFIX = "perf_"
RPC_BASE = 26102860


class PerfFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return PerfFakeExt()
