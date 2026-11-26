"""Sellado determinista de una copia de la sonda DayZSandbox_QA (brief F0.3-0 §4.1, §8.2(1))."""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wire


def stamp_probe_tree(src, dst):
    src_dir = Path(src).resolve()
    dst_dir = Path(dst).resolve()
    if not src_dir.is_dir():
        raise FileNotFoundError(f"source probe dir not found: {src_dir}")
    stamp = wire.compute_probe_stamp(src_dir)
    if src_dir != dst_dir:
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        dst_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_dir, dst_dir)
    stamp_file = dst_dir / wire.STAMP_REL_PATH
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    content = f'const string DSBX_QA_STAMP = "{stamp}";\n'
    stamp_file.write_bytes(content.encode("utf-8"))
    return stamp


def build_parser():
    p = argparse.ArgumentParser(prog="stamp_probe.py")
    p.add_argument("--src", required=True, help="Carpeta fuente de DayZSandbox_QA")
    p.add_argument("--dst", required=True, help="Carpeta destino de empaquetado")
    return p


def main(argv=None):
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    stamp = stamp_probe_tree(args.src, args.dst)
    print(stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
