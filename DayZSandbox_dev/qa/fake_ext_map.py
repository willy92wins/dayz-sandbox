"""Extension esqueleto de S-mapa para fake_peer (prefijo map_, RPC 26102870..26102879)."""

from fake_peer import FakeExt

PREFIX = "map_"
RPC_BASE = 26102870


class MapFakeExt(FakeExt):
    def handles(self, verb, role):
        return False


def create_ext(peer, jobs):
    return MapFakeExt()
