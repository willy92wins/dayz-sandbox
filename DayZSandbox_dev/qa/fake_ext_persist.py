"""Extension esqueleto de S-persist para fake_peer (prefijo per_, RPC 26102800..26102809)."""

from fake_peer import FakeExt

PREFIX = "per_"
RPC_BASE = 26102800


class PersistFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return PersistFakeExt()
