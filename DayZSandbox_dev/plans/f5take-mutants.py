"""F5 parte 1 §6: mutaciones M1-M14 del lado Python. Cada una se aplica, corre solo su prueba y se restaura.

Uso, desde DayZSandbox_dev/:  python3 plans/f5take-mutants.py [M1,M5,...]
Sale 0 si mueren todas las elegidas. No corras otra suite a la vez.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BR = "app/backend/bridge.py"
TL = "app/backend/take_live.py"
SV = "app/backend/server.py"
T = "app.tests.test_f5_take."

MUTANTS = [
    ("M1", BR, '            if verb == "take.stop":\n                order["priority"] = -1\n', "", T + "T4StopPrimero"),
    ("M2", TL, "                if last is None or (now - last) * 1000.0 >= TAKE_READ_MS:", "                if False:",
     T + "T2Rodar"),
    ("M3", BR, "                if tl is not None:\n                    tl.on_server_hello_locked(self.peers[peer])\n", "",
     T + "T11EpochNuevo"),
    ("M4", TL, '            if bad:\n                self._finish_locked("fallida", reason="checks")',
     '            if False:\n                self._finish_locked("fallida", reason="checks")', T + "T7Lecturas"),
    ("M5", TL, '        if snap["rev"] != t["rev"] or snap["hash"] != t["hash"]:', '        if False:',
     T + "T9DocCambia"),
    ("M6", TL, 'if t is None or t["state"] != "preparando" or t.get("stop_requested"):',
     'if t is None or t["state"] != "preparando":', T + "T10bStopAntesDeArmar"),
    ("M7", TL, '                or last.get("rev") != snap["rev"] or last.get("hash") != snap["hash"]:',
     '                or False:', T + "T8Errores.test_t8_errores_en_orden_y_sin_encolar"),
    ("M8", TL, "        if len(all_keys) < 2:", "        if len(all_keys) < 1:",
     T + "T8Errores.test_t8_errores_en_orden_y_sin_encolar"),
    ("M9", TL, "hexdigest()[:16]", "hexdigest()[:12]", T + "T1Preparar"),
    ("M10", TL, '    if (origin != "") != (state == "parada"):\n        return False\n', "", T + "V1Lecturas"),
    ("M11", TL, 'if t["state"] != "armada" or t.get("stop_requested"):', 'if t.get("stop_requested"):',
     T + "T2Rodar"),
    ("M12", SV, '                self.send_json(403, fail("forbidden", "Solo la persona para la toma"))\n                return\n',
     "                pass\n", T + "T12Credenciales"),
    ("M13", BR, '                    if tl is not None:\n                        tl.on_dropped_locked(order, "sin_resultado")\n', "",
     T + "T14Descartada"),
    ("M14", TL, '        if self._live():\n            return _fail("take_busy"', '        if False:\n            return _fail("take_busy"',
     T + "T8Errores.test_t8_errores_en_orden_y_sin_encolar"),
]


def main():
    pick = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    alive = []
    for mid, rel, old, new, test in MUTANTS:
        if pick and mid not in pick:
            continue
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if text.count(old) != 1:
            raise SystemExit("%s: el ancla aparece %d veces en %s" % (mid, text.count(old), rel))
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.replace(old, new))
            rc = subprocess.run([sys.executable, "-m", "unittest", test], cwd=ROOT,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        print("%s %s" % (mid, "muerta" if rc != 0 else "VIVA"), flush=True)
        if rc == 0:
            alive.append(mid)
    print("vivas: %s" % (",".join(alive) or "ninguna"))
    return 1 if alive else 0


if __name__ == "__main__":
    sys.exit(main())
