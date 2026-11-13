"""Préstamo de uso de la persona (F1-co §1): mientras viva, la IA recibe busy_human."""
import time


class Leases:
    def __init__(self, clock=time.monotonic, ttl=3.0):
        self.clock = clock
        self.ttl = ttl
        self._live = {}  # lease_id -> {"lease_id", "target", "field", "expires"}
        self._n = 0

    def take(self, target, field):
        self._n += 1
        lease = {"lease_id": "l-%d" % self._n, "target": target, "field": field,
                 "expires": self.clock() + self.ttl}
        self._live[lease["lease_id"]] = lease
        return dict(lease)

    def expire(self):
        """Quita las caducadas y las devuelve (cada una una sola vez)."""
        now = self.clock()
        gone = [l for l in self._live.values() if l["expires"] <= now]
        for l in gone:
            del self._live[l["lease_id"]]
        return gone

    def renew(self, lease_id):
        lease = self._live.get(lease_id)
        if lease is None or lease["expires"] <= self.clock():
            return None
        lease["expires"] = self.clock() + self.ttl
        return dict(lease)

    def release(self, lease_id):
        return self._live.pop(lease_id, None)

    def live(self):
        now = self.clock()
        return [dict(l) for l in self._live.values() if l["expires"] > now]

    def busy(self, fp):
        """Primera (target, field) de la huella que cruza una lease viva, o None."""
        for target, field in fp:
            for l in self.live():
                if l["target"] == target and (l["field"] is None or field == "*" or l["field"] == field):
                    return target, field
        return None
