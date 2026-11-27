"""F3-web §6: mutaciones W1-W12. Cada una se aplica, se corre solo lo que la debe matar y se restaura.

Uso, desde DayZSandbox_dev/ con NODE_PATH y PLAYWRIGHT_BROWSERS_PATH del gate:
    python3 plans/f3web-mutants.py [W1,W5,...]
Sale 0 si mueren todas las elegidas. No corras otra suite a la vez.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PP = "app/web/src/panels/PropertiesPanel.tsx"
AP = "app/web/src/panels/AddPanel.tsx"
ST = "app/web/src/store.ts"
PR = "app/backend/profile.py"

# (id, [(fichero, viejo, nuevo, veces)], filas E2E, pruebas unitarias)
MUTANTS = [
    ("W1", [(AP, "{ kind: 'actor', label: 'Actores', singular: 'Actor' },",
             "{ kind: 'actor', label: 'Actores', singular: 'Actor', disabled: true },", 1)], "AC1", None),
    ("W2", [(ST, "    args.marks = [];\n", "", 1)], "AC1", None),
    ("W3", [(AP, "const isRowDisabled = atCap || sinBackend || noWardrobes;",
             "const isRowDisabled = sinBackend || noWardrobes;", 1),
            (AP, "    if (atCap) {", "    if (false) {", 1),
            (ST, "  if (typeof cap === 'number' && count >= cap) {\n    setState({ placingItem: null });",
             "  if (false) {\n    setState({ placingItem: null });", 1)], "AC1", None),
    ("W4", [(PP, "catalog?.wardrobe_items?.[String(entityForCls.wardrobe ?? '')]",
             "catalog?.wardrobe_items?.[String(catalog?.wardrobes?.[0] ?? '')]", 1)], "AC2", None),
    ("W5", [(PR, '            "wardrobe_items": wardrobe_items,\n', "", 1)], "AC2", "test_catalog_actores.py"),
    ("W6", [(PP, "if (typeof parsedValue !== 'number' || parsedValue <= 0) {",
             "if (typeof parsedValue !== 'number') {", 1)], "AC3", None),
    ("W7", [(PP, "          list[idx] = { ...list[idx], [axis]: num };\n          return [\n            { name: 'entity.marks', target: ent.id, args: { marks: list } },",
             "          list[idx] = { ...list[idx], [axis]: num };\n          return [\n            { name: 'entity.marks', target: ent.id, args: { marks: [list[idx]] } },", 1)], "AC4", None),
    ("W8", [(PP, "return { emote: g.emote, at: g.at - 1 };", "return { emote: g.emote, at: g.at };", 1)], "AC5", None),
    ("W9", [(PP, "      if (usedBy >= 0) return;\n", "", 1),
            (PP, "const blocked = usedBy >= 0;", "const blocked = false;", 1)], "AC5", None),
    # La primera versión (en changeGestureWhen) era equivalente: commitGestures normaliza con gestureWire.
    ("W10", [(PP, "if (typeof g.at === 'number') return { emote: g.emote, at: g.at };",
              "if (typeof g.at === 'number') return Object.assign({ t: 0 }, { emote: g.emote, at: g.at });", 1)], "AC6", None),
    ("W11", [(PP, "num > marks.length", "num > 999", 1)], "AC6", None),
    ("W12", [(PP, "                <span>{ent.name}</span>", "                <span dangerouslySetInnerHTML={{ __html: ent.name }} />", 1)], "AC8", None),
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
                env = dict(os.environ, DSBX_GUION="actores", DSBX_ONLY=rows)
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
