"""Extension esqueleto de S3 para fake_peer (prefijo act_, RPC 26102810..26102819)."""

from fake_peer import FakeExt

PREFIX = "act_"
RPC_BASE = 26102810


class ActorFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return ActorFakeExt()
