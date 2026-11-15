"""Extension esqueleto de S-cam para fake_peer (prefijo scam_, RPC 26102820..26102829)."""

from fake_peer import FakeExt

PREFIX = "scam_"
RPC_BASE = 26102820


class CamFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return CamFakeExt()
