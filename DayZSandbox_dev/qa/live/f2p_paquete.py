#!/usr/bin/env python3
"""Paquete autocontenido para el portatil (R2-04).

Monta en un directorio el runner, las librerias auxiliares, los PBO y
los JSON, con manifest.json: por fichero, origen y sha256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_package(dest, items):
    """items: lista de (origen, nombre_en_paquete). Devuelve el manifest."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for origen, nombre in items:
        src = Path(origen)
        if not src.is_file():
            rows.append({"file": str(nombre), "origin": str(src),
                         "sha256": None, "missing": True})
            continue
        out = dest / nombre
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
        rows.append({"file": str(nombre), "origin": str(src.resolve()),
                     "sha256": sha256_file(out), "missing": False})
    manifest = {"files": rows}
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return manifest


def default_items(live_dir, *, lib_reinicio="", probe_lib="", pbo_dir=""):
    live = Path(live_dir)
    items = [
        (live / "f2p_partida.py", "f2p_partida.py"),
        (live / "f2p_tap.py", "f2p_tap.py"),
        (live / "f2p_fases.py", "f2p_fases.py"),
        (live / "f2p_paquete.py", "f2p_paquete.py"),
        (live / "f2p_server_ctl.ps1", "f2p_server_ctl.ps1"),
        (live / "run_f2p_partida.ps1", "run_f2p_partida.ps1"),
        (live / "LEEME_portatil.md", "LEEME_portatil.md"),
    ]
    if lib_reinicio:
        items.append((Path(lib_reinicio), "lib_reinicio_caja.ps1"))
    if probe_lib:
        items.append((Path(probe_lib), "probe-lib.ps1"))
    if pbo_dir:
        # Carpetas de mod con addons\ (F2 ronda 2b, modelo run_smoke_t3.ps1:158):
        # pbo/@DayZSandbox/addons/DayZSandbox.pbo y el QA equivalente.
        mod_for = {"DayZSandbox.pbo": "@DayZSandbox",
                   "DayZSandbox_QA.pbo": "@DayZSandbox_QA"}
        for pbo in sorted(Path(pbo_dir).glob("*.pbo")):
            mod = mod_for.get(pbo.name)
            if mod:
                items.append((pbo, "pbo/%s/addons/%s" % (mod, pbo.name)))
            else:
                items.append((pbo, "pbo/" + pbo.name))
        for mod_dir in sorted(Path(pbo_dir).glob("@*")):
            if mod_dir.is_dir():
                for pbo in sorted((mod_dir / "addons").glob("*.pbo")):
                    items.append((pbo, "pbo/%s/addons/%s" % (mod_dir.name, pbo.name)))
        for js in sorted(Path(pbo_dir).glob("*.json")):
            items.append((js, "json/" + js.name))
    return items


def transfer_orders(package_dir="paquete", results_dir="resultados",
                    remote="portatil", remote_root="C:/dsbx-m1"):
    root = str(remote_root).replace("\\", "/")
    return [
        "scp -r %s/* %s:%s/" % (package_dir, remote, root),
        'ssh %s "powershell -NoProfile -ExecutionPolicy Bypass -File %s/run_f2p_partida.ps1 -Maquina portatil -DryRun:$false"'
        % (remote, root),
        "scp -r %s:%s/%s/* %s/" % (remote, root, results_dir, results_dir),
    ]


def build_parser():
    p = argparse.ArgumentParser(prog="f2p_paquete")
    p.add_argument("--out", required=True)
    p.add_argument("--live-dir", default=str(Path(__file__).resolve().parent))
    p.add_argument("--lib-reinicio", default="")
    p.add_argument("--probe-lib", default="")
    p.add_argument("--pbo-dir", default="")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    items = default_items(args.live_dir, lib_reinicio=args.lib_reinicio,
                          probe_lib=args.probe_lib, pbo_dir=args.pbo_dir)
    if args.dry_run:
        for origen, nombre in items:
            print("paquete: %s -> %s" % (origen, nombre))
        for line in transfer_orders():
            print(line)
        return 0
    manifest = build_package(args.out, items)
    print(json.dumps({"out": args.out, "files": len(manifest["files"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
