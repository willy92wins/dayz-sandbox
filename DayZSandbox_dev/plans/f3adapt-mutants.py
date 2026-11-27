"""Mutantes X1..X13 de antitautologia para F3-adaptador (§7, reglas E1-E9)."""

import re
import shutil
import sys
import tempfile
from pathlib import Path

DEV_DIR = Path(__file__).resolve().parents[1]
REPO = DEV_DIR.parent
if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))

from app.tests.test_exp_adapter_static import ALL_CHECKS  # noqa: E402

ADAPTER_DIR = REPO / "DayZSandbox_Expansion"
CORE_DIR = REPO / "DayZSandbox"

# (id, descripcion, fichero_relativo_al_repo, patron_regex, reemplazo, regla_esperada, extra_file)
MUTANTS = (
    (
        "X1",
        'requiredAddons sin "DayZExpansion_AI_Scripts"',
        "DayZSandbox_Expansion/config.cpp",
        r',\s*"DayZExpansion_AI_Scripts"',
        "",
        "E1",
        None,
    ),
    (
        "X2",
        "un fichero .c de mas en scripts/4_World/ (fuera de la guarda)",
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r"(#ifdef\s+EXPANSIONMODAI\b)",
        r"\1",
        "E1",
        ("DayZSandbox_Expansion/scripts/4_World/DSBX_Extra.c", "void DsbxExtra() {}\n"),
    ),
    (
        "X3",
        "una funcion fuera del #ifdef al final de DSBX_ExpMission.c",
        "DayZSandbox_Expansion/scripts/5_Mission/DSBX_ExpMission.c",
        r"#endif\s*\Z",
        "#endif\nvoid DsbxOutsideGuard() {}\n",
        "E2",
        None,
    ),
    (
        "X4",
        'Name devuelve "none"',
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r'return\s+"expansion"\s*;',
        'return "none";',
        "E3",
        None,
    ),
    (
        "X5",
        "Register antes de super.OnMissionStart()",
        "DayZSandbox_Expansion/scripts/5_Mission/DSBX_ExpMission.c",
        r"(super\.OnMissionStart\(\)\s*;)([\s\S]*?)(DSBX_ActorEngineRegistry\.Register\([^;]+;\s*)",
        r"\2\3\1",
        "E4",
        None,
    ),
    (
        "X6",
        "sin ECE_NOLIFETIME",
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r"\|\s*ECE_NOLIFETIME\b|\bECE_NOLIFETIME\s*\|",
        "",
        "E5",
        None,
    ),
    (
        "X7",
        "eAIWaypointBehavior.ROAMING_LOCAL en ROAM",
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r'("ROAM")',
        r'"ROAM" /* */ && eAIWaypointBehavior.ROAMING_LOCAL != -1',
        "E6",
        None,
    ),
    (
        "X8",
        "Expansion_SetEmote(emoteId, true, 0)",
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r"Expansion_SetEmote\(\s*(\w+)\s*,\s*false\s*,\s*0\s*\)",
        r"Expansion_SetEmote(\1, true, 0)",
        "E6",
        None,
    ),
    (
        "X9",
        "EmoteHeart borrado de EmoteId",
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r'[ \t]*if\s*\(\s*emote\s*==\s*"EmoteHeart"\s*\)\s*(?:\{\s*)?return\s+EmoteConstants\.ID_EMOTE_HEART\s*;(?:\s*\})?\r?\n?',
        "",
        "E7",
        None,
    ),
    (
        "X10",
        "EmotePoint con ID_EMOTE_THUMB",
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r'(if\s*\(\s*emote\s*==\s*"EmotePoint"\s*\)\s*(?:\{\s*)?return\s+EmoteConstants\.)ID_EMOTE_POINT\b',
        r"\1ID_EMOTE_THUMB",
        "E7",
        None,
    ),
    (
        "X11",
        "RequestGesture del nucleo con la firma de tres argumentos",
        "DayZSandbox/scripts/3_Game/DSBX_ActorEngine.c",
        r"string\s+RequestGesture\s*\(\s*string\s+lid\s*,\s*int\s+gi\s*,\s*string\s+emote\s*,\s*int\s+atMark\s*,\s*int\s+tMs\s*\)",
        "string RequestGesture(string lid, int gi, string emote)",
        "E8",
        None,
    ),
    (
        "X12",
        "ReadJson con gestures vacio fijo",
        "DayZSandbox/scripts/3_Game/DSBX_ActorOps.c",
        r'return\s+"\{\\"actors\\":\["\s*\+\s*rows\s*\+\s*"\],\\"gestures\\":\["\s*\+\s*\w+\s*\+\s*"\]\}"\s*;',
        'return "{\\"actors\\":[" + rows + "],\\"gestures\\":[]}";',
        "E8",
        None,
    ),
    (
        "X13",
        'causa "Timeout"',
        "DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c",
        r'"timeout"',
        '"Timeout"',
        "E9",
        None,
    ),
)


def _run_mutant(mid: str, desc: str, rel_file: str, pattern: str, repl: str, rule: str, extra) -> bool:
    """Ejecuta un mutante sobre una copia temporal y devuelve True solo si muere con su regla."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        tmp_core = tmp_root / "DayZSandbox"
        tmp_adapter = tmp_root / "DayZSandbox_Expansion"

        if CORE_DIR.is_dir():
            shutil.copytree(CORE_DIR, tmp_core)
        if ADAPTER_DIR.is_dir():
            shutil.copytree(ADAPTER_DIR, tmp_adapter)

        target = tmp_root / rel_file
        if not target.is_file():
            print(f"{mid} ({rule}): SIN_ANCLA - no existe {rel_file} [{desc}]")
            return False

        text = target.read_bytes().decode("utf-8", errors="replace")
        if not re.search(pattern, text, flags=re.MULTILINE):
            print(f"{mid} ({rule}): SIN_ANCLA - patron no encontrado en {rel_file} [{desc}]")
            return False

        mutated = re.sub(pattern, repl, text, count=1, flags=re.MULTILINE)
        target.write_bytes(mutated.encode("utf-8"))

        if extra is not None:
            extra_rel, extra_content = extra
            extra_path = tmp_root / extra_rel
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_bytes(extra_content.encode("utf-8"))

        failed = [name for name, fn in ALL_CHECKS.items() if fn(tmp_adapter, tmp_core)]
        if mid == "X2":
            killed = "E1" in failed and all(r in ("E1", "E2") for r in failed)
        else:
            killed = failed == [rule]

        status = "MUERTO" if killed else "VIVO"
        print(f"{mid} ({rule}): {status} - fallaron={failed} [{desc}]")
        return killed


def main() -> int:
    killed_count = 0
    for entry in MUTANTS:
        if _run_mutant(*entry):
            killed_count += 1
    total = len(MUTANTS)
    print(f"Resumen: {killed_count}/{total} mutantes muertos.")
    return 0 if killed_count == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
