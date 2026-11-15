"""PBO del mod nucleo DayZSandbox/ desde HEAD limpio (brief de F1b-peers §5.3).

Uso, desde DayZSandbox_dev/:
    C:\\Python314\\python.exe qa/build_core_pbo.py --out <carpeta nueva> [--addon-builder <ruta>]

1. Exige el repo limpio (git status --porcelain vacio) y toma HEAD.
2. Saca DayZSandbox/ de HEAD con `git -c core.autocrlf=false archive` a <out>/stage.
3. Empaqueta con AddonBuilder, siempre con lista de argumentos y sin shell.
4. Lee el PBO y lo compara con HEAD por sha256: lleva exactamente los ficheros de
   DayZSandbox/ en HEAD, $PBOPREFIX$ e include.lst incluidos (AddonBuilder los mete; medido
   el 2026-11-15 sobre 5c31a55), y el prefijo DayZSandbox.
5. Comprueba que el repo sigue limpio.

Escribe <out>/build_core_pbo.json. Sale con 0 si todo cuadra, con 1 si hay diferencias y
con 2 si falta una precondicion (repo sucio, sin git, sin AddonBuilder o --out con algo dentro).
El patron es build_pbo.py de F0.3-0, que vive fuera del repo.
"""
import argparse
import hashlib
import io
import json
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

AB_DEFAULT = r"C:\Program Files (x86)\Steam\steamapps\common\DayZ Tools\Bin\AddonBuilder\AddonBuilder.exe"
MOD = "DayZSandbox"
PRODUCT = 0x56657273  # metodo de la entrada de producto ("Vers")
REPO = Path(__file__).resolve().parents[2]


class Precondition(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, binary=True):
    try:
        p = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True)
    except OSError as e:
        raise Precondition("sin git: %s" % e)
    if p.returncode != 0:
        raise Precondition("git %s: %s" % (args[0], p.stderr.decode("utf-8", "replace").strip()))
    return p.stdout if binary else p.stdout.decode("utf-8", "replace").strip()


def _parse(pbo):
    """(props, [(nombre, tamano)], inicio de los datos) de los bytes de un PBO sin comprimir."""
    i, entries, props = 0, [], {}

    def cstr(j):
        k = pbo.find(b"\x00", j)
        if k < 0:
            raise ValueError("cabeceras del PBO sin terminar")
        return pbo[j:k].decode("utf-8"), k + 1

    try:
        while True:
            name, i = cstr(i)
            method, _orig, _res, _ts, size = struct.unpack_from("<5I", pbo, i)
            i += 20
            if name == "" and method == PRODUCT:
                while True:
                    k, i = cstr(i)
                    if not k:
                        break
                    v, i = cstr(i)
                    props[k] = v
                continue
            if name == "":
                break
            if method != 0:
                raise ValueError("entrada comprimida o desconocida: %s" % name)
            entries.append((name, size))
    except (struct.error, UnicodeDecodeError) as e:
        raise ValueError("cabeceras del PBO rotas: %s" % e)
    return props, entries, i


def read_pbo(path):
    """(prefix, {nombre con /: bytes}) de un PBO sin comprimir. ValueError si esta roto."""
    pbo = Path(path).read_bytes()
    props, entries, data = _parse(pbo)
    files = {}
    for name, size in entries:
        if data + size > len(pbo):
            raise ValueError("PBO truncado en %s" % name)
        files[name.replace("\\", "/")] = pbo[data:data + size]
        data += size
    return props.get("prefix", ""), files


def pbo_checksum_ok(path):
    """Si los 21 bytes finales son 0x00 + SHA-1 de todo lo anterior (informativo)."""
    pbo = Path(path).read_bytes()
    _props, entries, data = _parse(pbo)
    end = data + sum(size for _n, size in entries)
    tail = pbo[end:]
    return len(tail) == 21 and tail[0] == 0 and tail[1:] == hashlib.sha1(pbo[:end]).digest()


def compare(head_files, pbo_files):
    """Diferencias entre lo que debe llevar el PBO (los ficheros de HEAD) y lo que lleva."""
    want = dict(head_files)
    out = [{"path": p, "problem": "missing"} for p in sorted(set(want) - set(pbo_files))]
    out += [{"path": p, "problem": "extra"} for p in sorted(set(pbo_files) - set(want))]
    for p in sorted(set(want) & set(pbo_files)):
        a, b = sha256(want[p]), sha256(pbo_files[p])
        if a != b:
            out.append({"path": p, "problem": "different", "head_sha256": a, "pbo_sha256": b})
    return out


def head_files(head):
    names = git("ls-tree", "-r", "--name-only", "-z", head, "--", MOD).split(b"\x00")
    files = {}
    for raw in names:
        if raw:
            name = raw.decode("utf-8")
            files[name[len(MOD) + 1:]] = git("show", "%s:%s" % (head, name))
    return files


def build(out, ab):
    log = {"ok": False, "head": None, "prefix": None, "pbo": None, "pbo_sha256": None,
           "files": [], "mismatches": []}
    if not Path(ab).is_file():
        raise Precondition("sin AddonBuilder en %s" % ab)
    if git("status", "--porcelain", binary=False):
        raise Precondition("repo sucio")
    head = git("rev-parse", "HEAD", binary=False)
    if out.exists() and any(out.iterdir()):
        raise Precondition("--out ya tiene algo dentro")
    log["head"] = head
    out.mkdir(parents=True, exist_ok=True)
    tar = git("-c", "core.autocrlf=false", "archive", "--format=tar", head, MOD)
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        tf.extractall(out / "stage", filter="data")
    addons = out / ("@" + MOD) / "Addons"
    addons.mkdir(parents=True)
    cmd = [str(ab), str(out / "stage" / MOD), str(addons), "-prefix=" + MOD,
           "-temp=" + str(out / "abtmp"), "-clear", "-packonly"]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=600)
    log["addonbuilder_rc"] = p.returncode
    log["addonbuilder_tail"] = (p.stdout + p.stderr).strip().splitlines()[-3:]
    pbo = addons / (MOD + ".pbo")
    if p.returncode != 0 or not pbo.is_file():
        log["mismatches"].append({"problem": "addonbuilder", "rc": p.returncode})
        return log
    log["pbo"] = str(pbo)
    log["pbo_sha256"] = sha256(pbo.read_bytes())
    try:
        prefix, files = read_pbo(pbo)
        log["pbo_checksum_ok"] = pbo_checksum_ok(pbo)
    except ValueError as e:
        log["mismatches"].append({"problem": "pbo_unreadable", "detail": str(e)})
        return log
    log["prefix"] = prefix
    log["files"] = [{"path": k, "bytes": len(v), "sha256": sha256(v)} for k, v in sorted(files.items())]
    log["mismatches"] = compare(head_files(head), files)
    if prefix != MOD:
        log["mismatches"].append({"problem": "prefix", "pbo": prefix})
    if git("status", "--porcelain", binary=False):
        log["mismatches"].append({"problem": "repo_dirty_after"})
    log["ok"] = not log["mismatches"]
    return log


def main(argv=None):
    ap = argparse.ArgumentParser(description="Construye y comprueba el PBO de DayZSandbox/.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--addon-builder", default=AB_DEFAULT)
    args = ap.parse_args(argv)
    out = Path(args.out)
    try:
        log = build(out, args.addon_builder)
    except Precondition as e:
        print("build_core_pbo: " + str(e), file=sys.stderr)
        return 2
    (out / "build_core_pbo.json").write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8", newline="\n")
    print(json.dumps({k: log[k] for k in ("ok", "head", "prefix", "pbo_sha256", "mismatches")},
                     ensure_ascii=False))
    return 0 if log["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
