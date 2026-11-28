"""F3-foto §5: mutaciones P1-P5 sobre scene_plan.py; cada una corre test_actor_photo_cap.py y se restaura."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SP = os.path.join(ROOT, "app/backend/scene_plan.py")
MUTANTS = [
    ("P1", "        if photo_len > WIRE_CAP:\n", "        if False:\n"),
    ("P2", "            continue\n        aid = ent.get(\"id\")\n        items = wardrobes",
           "            continue\n        if rows:\n            break\n        aid = ent.get(\"id\")\n        items = wardrobes"),
    ("P3", "            events.append([aid, j, \"playing\", t_ms, None])\n", ""),
    ("P4", "        if photo_len > WIRE_CAP:\n", "        if photo_len >= WIRE_CAP:\n"),
    ("P5", "    if not errors and n_actors > 0:\n", "    if n_actors > 0:\n"),
]


def main():
    with open(SP, encoding="utf-8") as f:
        orig = f.read()
    alive = []
    try:
        for mid, old, new in MUTANTS:
            assert orig.count(old) == 1, mid
            with open(SP, "w", encoding="utf-8") as f:
                f.write(orig.replace(old, new))
            rc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "app/tests", "-t", "app",
                                 "-p", "test_actor_photo_cap.py"], cwd=ROOT,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
            print(mid, "MUERE" if rc else "VIVE", flush=True)
            if not rc:
                alive.append(mid)
    finally:
        with open(SP, "w", encoding="utf-8") as f:
            f.write(orig)
    print("vivas:", ",".join(alive) or "ninguna")
    return 1 if alive else 0


if __name__ == "__main__":
    sys.exit(main())
