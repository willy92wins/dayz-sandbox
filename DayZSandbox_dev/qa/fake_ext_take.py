"""Extension esqueleto de S-toma para fake_peer (prefijo take_, RPC 26102850..26102859)."""

from fake_peer import FakeExt

PREFIX = "take_"
RPC_BASE = 26102850


class TakeFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return TakeFakeExt()
