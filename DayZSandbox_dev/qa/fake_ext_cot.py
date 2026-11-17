"""Extension esqueleto de S-cot para fake_peer (prefijo cot_, RPC 26102830..26102839)."""

from fake_peer import FakeExt

PREFIX = "cot_"
RPC_BASE = 26102830


class CotFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return CotFakeExt()
