"""PBO sellado de F0.3-0 (§8.2, puntos 1-2) desde un commit limpio.

Uso: C:\\Python314\\python.exe build_pbo.py <worktree> <outdir>
1. Exige el worktree limpio (git status --porcelain vacio) y toma HEAD.
2. Extrae la sonda de HEAD con `git archive` a <outdir>/stage/DayZSandbox_QA (copia desde arbol limpio).
3. Ejecuta qa/stamp_probe.py --src <repo probe> --dst <stage>; compara el sello con
   f03_common.compute_probe_stamp_at_commit(HEAD).
4. Empaqueta <stage> con AddonBuilder (siempre con argumentos, -packonly).
5. Lee el PBO y compara cada fichero con <stage> byte a byte; calcula sha256.
6. Comprueba que el repo sigue limpio y con DSBX_QA_Stamp.c = "unstamped".
"""
import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

PY = r"C:\Python314\python.exe"
AB = r"C:\Program Files (x86)\Steam\steamapps\common\DayZ Tools\Bin\AddonBuilder\AddonBuilder.exe"
PROBE_REL = "DayZSandbox_dev/qa/probe/DayZSandbox_QA"


def git(wt, *args, binary=False):
    p = subprocess.run(["git", "-C", str(wt), *args], capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} fallo: {p.stderr.decode(errors='replace')}")
    return p.stdout if binary else p.stdout.decode("utf-8", "replace").strip()


def read_pbo(path):
    pbo = path.read_bytes()
    i, entries, props = 0, [], {}

    def cstr(j):
        k = pbo.index(b"\x00", j)
        return pbo[j:k].decode("utf-8", "replace"), k + 1
    while True:
        name, i = cstr(i)
        method, orig, res, ts, size = struct.unpack_from("<5I", pbo, i)
        i += 20
        if name == "" and method == 0x56657273:
            while True:
                k, i = cstr(i)
                if not k:
                    break
                v, i = cstr(i)
                props[k] = v
            continue
        if name == "":
            break
        entries.append((name, method, size))
    data, files = i, {}
    for name, method, size in entries:
        files[name.replace("\\", "/")] = (method, pbo[data:data + size])
        data += size
    return props, files


def main():
    wt = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=False)
    log = {}
    if git(wt, "status", "--porcelain") != "":
        raise SystemExit("worktree sucio: no se empaqueta")
    head = git(wt, "rev-parse", "HEAD")
    log["git_head"] = head
    # 2. copia desde arbol limpio: exactamente lo confirmado en HEAD
    tar_bytes = git(wt, "archive", "--format=tar", head, PROBE_REL, binary=True)
    stage_root = out / "stage"
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
        tf.extractall(stage_root, filter="data")
    staged = stage_root / PROBE_REL
    stage = out / "stage_flat" / "DayZSandbox_QA"
    shutil.copytree(staged, stage)
    shutil.rmtree(stage_root)
    # 3. sello
    dz = wt / "DayZSandbox_dev"
    p = subprocess.run([PY, "qa/stamp_probe.py", "--src", "qa/probe/DayZSandbox_QA", "--dst", str(stage)],
                       cwd=str(dz), capture_output=True, text=True)
    log["stamp_probe_rc"] = p.returncode
    log["stamp_probe_stdout"] = p.stdout.strip()
    log["stamp_probe_stderr"] = p.stderr.strip()
    if p.returncode != 0:
        raise SystemExit(f"stamp_probe fallo: {p.stderr}")
    stamp = p.stdout.strip().splitlines()[-1].strip()
    q = subprocess.run([PY, "-c", "import sys; sys.path.insert(0, 'qa'); import f03_common; "
                        f"print(f03_common.compute_probe_stamp_at_commit('{head}'))"],
                       cwd=str(dz), capture_output=True, text=True)
    expected = q.stdout.strip()
    log["stamp"] = stamp
    log["stamp_expected_at_head"] = expected
    log["stamp_match"] = stamp == expected and len(stamp) == 16
    stamp_c = (stage / "scripts/5_Mission/DSBX_QA_Stamp.c").read_bytes()
    log["stage_stamp_c"] = stamp_c.decode("utf-8")
    log["stage_stamp_c_ok"] = stamp_c == f'const string DSBX_QA_STAMP = "{stamp}";\n'.encode("utf-8")
    # resto del stage identico al repo
    diffs = []
    for f in sorted(stage.rglob("*")):
        if f.is_file():
            rel = f.relative_to(stage).as_posix()
            if rel == "scripts/5_Mission/DSBX_QA_Stamp.c":
                continue
            if f.read_bytes() != (dz / "qa/probe/DayZSandbox_QA" / rel).read_bytes():
                diffs.append(rel)
    log["stage_vs_repo_diffs"] = diffs
    # 4. AddonBuilder, siempre con argumentos
    addons = out / "@DayZSandbox_QA" / "Addons"
    addons.mkdir(parents=True)
    ab = subprocess.run([AB, str(stage), str(addons), "-prefix=DayZSandbox_QA",
                         f"-temp={out / 'abtmp'}", "-clear", "-packonly"],
                        capture_output=True, text=True, timeout=600)
    log["addonbuilder_rc"] = ab.returncode
    log["addonbuilder_tail"] = (ab.stdout + ab.stderr).strip().splitlines()[-3:]
    pbo = addons / "DayZSandbox_QA.pbo"
    if not pbo.exists():
        raise SystemExit(f"no hay PBO: {log}")
    # 5. comprobacion del PBO
    props, files = read_pbo(pbo)
    log["pbo_props"] = props
    want = {f.relative_to(stage).as_posix(): f.read_bytes() for f in stage.rglob("*") if f.is_file()}
    want_c = {k for k in want if k.endswith((".c", ".cpp"))}
    missing = sorted(k for k in want_c if k not in files)
    different = sorted(k for k in want_c if k in files and files[k][1] != want[k])
    extra = sorted(k for k in files if k not in want)
    log["pbo_files"] = sorted(files)
    log["pbo_missing_sources"] = missing
    log["pbo_different_sources"] = different
    log["pbo_extra"] = extra
    log["pbo_stamp_c"] = files.get("scripts/5_Mission/DSBX_QA_Stamp.c", (None, b""))[1].decode("utf-8")
    log["pbo_sha256"] = hashlib.sha256(pbo.read_bytes()).hexdigest()
    log["pbo_bytes"] = pbo.stat().st_size
    log["pbo_path"] = str(pbo)
    # 6. repo intacto
    log["repo_clean_after"] = git(wt, "status", "--porcelain") == ""
    log["repo_stamp_c"] = (dz / "qa/probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_Stamp.c").read_text(encoding="utf-8")
    log["ok"] = (log["stamp_match"] and log["stage_stamp_c_ok"] and not diffs and log["addonbuilder_rc"] == 0
                 and not missing and not different and log["repo_clean_after"]
                 and '"unstamped"' in log["repo_stamp_c"] and props.get("prefix") == "DayZSandbox_QA")
    (out / "build_pbo.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(log, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
