"""Extension esqueleto de S-tiempo para fake_peer (prefijo env_, RPC 26102840..26102849)."""

from fake_peer import FakeExt

PREFIX = "env_"
RPC_BASE = 26102840


class EnvFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return EnvFakeExt()
