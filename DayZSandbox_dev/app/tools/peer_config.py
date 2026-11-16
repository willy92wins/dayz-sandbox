"""Escribe la configuracion que lee el peer del mod (brief de F1b-peers §3.1).

Uso, desde DayZSandbox_dev/:
    C:\\Python314\\python.exe app/tools/peer_config.py --config <backend.json> --profile <carpeta>

Lee `peer_key` (16-128 caracteres de [A-Za-z0-9_-]) y `bridge_port` (1-65535, 8766 si falta)
de backend.json y escribe <carpeta>/dsbx_peer.json con
{"url": "http://127.0.0.1:<bridge_port>/", "key": "<peer_key>"}, en UTF-8 sin BOM y de forma
atomica. Sale con 0 si lo escribe y con 2 si algo no vale, sin escribir nada. La clave no se
imprime nunca: los mensajes dicen el motivo, no el valor.
"""
import argparse
import json
import os
import re
import sys
import tempfile

KEY_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")  # alfabeto de secrets.token_urlsafe
DEFAULT_PORT = 8766


def _fail(reason):
    print("peer_config: " + reason, file=sys.stderr)
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="Escribe dsbx_peer.json para el peer del mod.")
    ap.add_argument("--config")
    ap.add_argument("--profile")
    args = ap.parse_args(argv)
    if not args.config or not args.profile:
        return _fail("faltan --config o --profile")
    try:
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return _fail("no se puede leer --config como JSON")
    if not isinstance(cfg, dict):
        return _fail("--config no es un objeto JSON")
    key = cfg.get("peer_key")
    if not isinstance(key, str) or KEY_RE.fullmatch(key) is None:
        return _fail("peer_key falta o no tiene 16-128 caracteres de [A-Za-z0-9_-]")
    port = cfg.get("bridge_port", DEFAULT_PORT)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return _fail("bridge_port no es un entero entre 1 y 65535")
    data = json.dumps({"url": "http://127.0.0.1:%d/" % port, "key": key})
    try:
        os.makedirs(args.profile, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=args.profile, prefix=".dsbx_peer.", suffix=".tmp")
    except OSError:
        return _fail("no se puede escribir en --profile")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
        os.replace(tmp, os.path.join(args.profile, "dsbx_peer.json"))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return _fail("no se puede escribir dsbx_peer.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
