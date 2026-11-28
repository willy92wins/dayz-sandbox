"""F4-web §4: mutaciones V1-V12. Cada una se aplica, se corre solo lo que la debe matar y se restaura.

Uso, desde DayZSandbox_dev/ con NODE_PATH y PLAYWRIGHT_BROWSERS_PATH del gate:
    python3 plans/f3web-mutants.py [W1,W5,...]
Sale 0 si mueren todas las elegidas. No corras otra suite a la vez.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PP = "app/web/src/panels/PropertiesPanel.tsx"
CP = "app/web/src/panels/CamerasPanel.tsx"
HP = "app/web/src/panels/HierarchyPanel.tsx"
ST = "app/web/src/store.ts"
CL = "app/backend/camera_live.py"

# (id, [(fichero, viejo, nuevo, veces)], filas E2E, pruebas unitarias)
MUTANTS = [
    ("V1", [(CP, "if (keys.length <= 1) return 'Fija';", "if (keys.length <= 0) return 'Fija';", 1)], "CM1", None),
    ("V2", [(CP, "  fov: 50,\n", "  fov: 60,\n", 1)], "CM2", None),
    ("V3", [(PP, "if (field === 'fov') return num > 0 && num < 180;", "if (field === 'fov') return num > 0;", 1)], "CM3", None),
    ("V4", [(PP, "if (field === 'x' || field === 'z') return num >= 0 && num <= 15360;",
             "if (field === 'x' || field === 'z') return num <= 15360;", 1)], "CM3", None),
    ("V5", [(PP, "    if (!(num > prev)) return false;\n", "", 1)], "CM3", None),
    ("V6", [(PP, "list.push({ ...copyCameraKey(last), t: last.t + 1 });", "list.push({ ...copyCameraKey(last), t: last.t + 2 });", 1)], "CM4", None),
    ("V7", [(PP, "i === 0 ? { ...item, t: 0 } : { ...item, t: item.t - shift }", "i === 0 ? { ...item, t: 0 } : item", 1)], "CM4", None),
    ("V8", [(PP, "disabled={sinBackend || keys.length <= 1}", "disabled={sinBackend}", 1)], "CM4", None),
    ("V9", [(CP, "disabled={sinBackend || !selectedCam}", "disabled={sinBackend}", 1),
            (CP, "            if (!selectedCam) return;\n            void playCamera(selectedCam.id);",
             "            void playCamera(selectedCam ? selectedCam.id : '');", 1)], "CM5", None),
    ("V10", [(ST, "  if (key !== undefined) body.key = key;\n", "", 1)], "CM5", None),
    ("V11", [(CP, "  if (last && last.status === 'dropped') return 'La orden no llegó al juego';\n", "", 1)], "CM6", None),
    ("V12", [(CL, "            keys = [all_keys[key]]", "            keys = [all_keys[0]]", 1)], "CM5", "test_f4_camera.py"),
]


def run(cmd, env=None):
    p = subprocess.run(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout


def build():
    p = subprocess.run(["npm", "run", "build"], cwd=os.path.join(ROOT, "app/web"),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout


def main():
    pick = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    results = []
    for mid, edits, rows, unit in MUTANTS:
        if pick and mid not in pick:
            continue
        saved = {}
        try:
            for path, old, new, times in edits:
                full = os.path.join(ROOT, path)
                if full not in saved:
                    with open(full, encoding="utf-8") as f:
                        saved[full] = f.read()
                with open(full, encoding="utf-8") as f:
                    s = f.read()
                if s.count(old) != times:
                    raise SystemExit("%s: el ancla aparece %d veces en %s" % (mid, s.count(old), path))
                with open(full, "w", encoding="utf-8") as f:
                    f.write(s.replace(old, new))
            killed_by = []
            if unit:
                rc, _ = run([sys.executable, "-m", "unittest", "discover", "-s", "app/tests", "-t", "app", "-p", unit])
                if rc != 0:
                    killed_by.append(unit)
            if any(p.startswith("app/web/") for p, _o, _n, _t in edits):
                rc, out = build()
                if rc != 0:
                    killed_by.append("build")
            if not killed_by or unit:
                env = dict(os.environ, DSBX_GUION="camaras", DSBX_ONLY=rows)
                if "build" not in killed_by:
                    rc, out = run([sys.executable, "app/tests/e2e_studio.py"], env=env)
                    if rc != 0 or "FALLA" in out or "PARCIAL" not in out:
                        killed_by.append(rows)
            verdict = "MUERE" if killed_by else "VIVE"
            results.append((mid, verdict, killed_by))
            print("%s %s %s" % (mid, verdict, ",".join(killed_by)), flush=True)
        finally:
            for full, text in saved.items():
                with open(full, "w", encoding="utf-8") as f:
                    f.write(text)
    build()
    alive = [m for m, v, _k in results if v == "VIVE"]
    print("vivas: %s" % (",".join(alive) or "ninguna"))
    return 1 if alive else 0


if __name__ == "__main__":
    sys.exit(main())
