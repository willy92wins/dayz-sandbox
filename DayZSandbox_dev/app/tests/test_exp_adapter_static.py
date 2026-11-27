"""Comprobacion estatica del adaptador DayZSandbox_Expansion/ (F3-adaptador §6, reglas E1-E9)."""

import json
import re
import unittest
from pathlib import Path

from app.tests.test_mod_static import _find_class_body, _find_method_body, _strip_comments

REPO = Path(__file__).resolve().parents[3]
ADAPTER_DIR = REPO / "DayZSandbox_Expansion"
CORE_DIR = REPO / "DayZSandbox"
CATALOG_PATH = REPO / "DayZSandbox_dev/fixtures/catalog-m1.json"

adapter_dir = ADAPTER_DIR
core_dir = CORE_DIR

EXPECTED_ADAPTER_FILES = (
    "$PBOPREFIX$",
    "include.lst",
    "config.cpp",
    "scripts/4_World/DSBX_ExpEngine.c",
    "scripts/5_Mission/DSBX_ExpMission.c",
)

EXPECTED_REQUIRED_ADDONS = [
    '"DZ_Data"',
    '"DZ_Characters"',
    '"DayZSandbox"',
    '"DayZExpansion_Core_Scripts"',
    '"DayZExpansion_AI_Scripts"',
]

EXPECTED_DEPENDENCIES = [
    '"World"',
    '"Mission"',
]

EXPECTED_OVERRIDE_METHODS = (
    ("Name", "string"),
    ("IsAvailable", "bool"),
    ("Spawn", "string"),
    ("SetMarks", "string"),
    ("RequestGesture", "string"),
    ("State", "string"),
    ("Stop", "string"),
    ("Despawn", "string"),
    ("Gestures", "string"),
)

FORBIDDEN_ADAPTER_TOKENS = (
    "GetQuasiRandom",
    "ROAMING",
    "ECE_DYNAMIC_PERSISTENCY",
    "ExpansionHumanLoadout",
)

EXPECTED_EMOTE_PAIRS = [
    ("EmoteGreeting", "EmoteConstants.ID_EMOTE_GREETING"),
    ("EmotePoint", "EmoteConstants.ID_EMOTE_POINT"),
    ("EmoteThumb", "EmoteConstants.ID_EMOTE_THUMB"),
    ("EmoteSurrender", "EmoteConstants.ID_EMOTE_SURRENDER"),
    ("EmoteSalute", "EmoteConstants.ID_EMOTE_SALUTE"),
    ("EmoteFacepalm", "EmoteConstants.ID_EMOTE_FACEPALM"),
    ("EmoteTaunt", "EmoteConstants.ID_EMOTE_TAUNT"),
    ("EmoteHeart", "EmoteConstants.ID_EMOTE_HEART"),
]

VALID_CAUSES = frozenset({"timeout", "interrupted", "stop"})
VALID_EVENT_STATES = frozenset({
    "requested",
    "playing",
    "finished",
    "canceled",
    "rejected",
    "expired",
})
REQUIRED_EMITTED_STATES = frozenset({
    "requested",
    "playing",
    "finished",
    "canceled",
    "expired",
})
NON_EVENT_WORD_LITERALS = frozenset({
    "expansion",
    "none",
    "eAI_",
    "CfgVehicles",
    "unknown_class",
    "spawn_failed",
    "wardrobe_failed",
    "unknown_actor",
    "bad_behaviour",
    "bad_marks",
    "bad_position",
    "unknown_emote",
    "expansion_unavailable",
    "HOLD",
    "ONCE",
    "LOOP",
    "ROAM",
    "idle",
    "moving",
    "arrived",
    "unreachable",
    "null",
    "true",
    "false",
    "queued",
    "done",
    "pending",
    "waiting",
    *(name for name, _ in EXPECTED_EMOTE_PAIRS),
})


def _read_stripped(path: Path) -> str:
    """Lee un fichero UTF-8 y elimina comentarios C/Enforce."""
    return _strip_comments(path.read_bytes().decode("utf-8", errors="replace"))


def _extract_call_args(code: str, func_name: str) -> list[list[str]]:
    """Extrae la lista de argumentos de cada llamada a func_name(...)."""
    calls = []
    for m in re.finditer(rf"\b{re.escape(func_name)}\s*\(", code):
        open_idx = code.find("(", m.start())
        depth = 0
        in_str = False
        i = open_idx
        n = len(code)
        args = []
        arg_start = open_idx + 1
        while i < n:
            ch = code[i]
            if in_str:
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == '"':
                    in_str = False
                i += 1
                continue
            if ch == '"':
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    args.append(code[arg_start:i].strip())
                    calls.append(args)
                    break
            elif ch == "," and depth == 1:
                args.append(code[arg_start:i].strip())
                arg_start = i + 1
            i += 1
    return calls


def check_e1(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E1 forma: arbol exacto de DayZSandbox_Expansion, $PBOPREFIX$, include.lst y config.cpp."""
    adapter_dir = Path(adapter_dir)
    violations = []
    if not adapter_dir.is_dir():
        return [f"E1: no existe el directorio {adapter_dir}"]

    actual_files = sorted(
        p.relative_to(adapter_dir).as_posix() for p in adapter_dir.rglob("*") if p.is_file()
    )
    expected_files = sorted(EXPECTED_ADAPTER_FILES)
    if actual_files != expected_files:
        violations.append(
            f"E1: arbol de ficheros distinto: actual={actual_files} esperado={expected_files}"
        )

    pbo_prefix = adapter_dir / "$PBOPREFIX$"
    if pbo_prefix.is_file():
        txt = pbo_prefix.read_bytes().decode("utf-8", errors="replace").strip()
        if txt != "DayZSandbox_Expansion":
            violations.append(f"E1: $PBOPREFIX$ debe ser 'DayZSandbox_Expansion', es '{txt}'")

    inc_lst = adapter_dir / "include.lst"
    if inc_lst.is_file():
        txt = inc_lst.read_bytes().decode("utf-8", errors="replace").strip()
        if txt != "*.c":
            violations.append(f"E1: include.lst debe ser '*.c', es '{txt}'")

    cfg_path = adapter_dir / "config.cpp"
    if not cfg_path.is_file():
        violations.append("E1: falta config.cpp")
        return violations

    cfg = _read_stripped(cfg_path)
    m_req = re.search(r"\brequiredAddons\s*\[\s*\]\s*=\s*\{([^}]*)\}\s*;", cfg)
    if not m_req:
        violations.append("E1: falta requiredAddons[] en config.cpp")
    else:
        items = [s.strip() for s in m_req.group(1).split(",") if s.strip()]
        if items != EXPECTED_REQUIRED_ADDONS:
            violations.append(
                f"E1: requiredAddons distinto: actual={items} esperado={EXPECTED_REQUIRED_ADDONS}"
            )

    m_dep = re.search(r"\bdependencies\s*\[\s*\]\s*=\s*\{([^}]*)\}\s*;", cfg)
    if not m_dep:
        violations.append("E1: falta dependencies[] en config.cpp")
    else:
        deps = [s.strip() for s in m_dep.group(1).split(",") if s.strip()]
        if deps != EXPECTED_DEPENDENCIES:
            violations.append(
                f"E1: dependencies distinto: actual={deps} esperado={EXPECTED_DEPENDENCIES}"
            )

    defs_body = _find_class_body(cfg, "defs")
    if not defs_body:
        violations.append("E1: config.cpp no tiene class defs")
    else:
        subclasses = re.findall(r"\bclass\s+(\w+)\b", defs_body)
        if sorted(subclasses) != ["missionScriptModule", "worldScriptModule"]:
            violations.append(
                f"E1: defs debe tener solo worldScriptModule y missionScriptModule, tiene {subclasses}"
            )
        world_body = _find_class_body(defs_body, "worldScriptModule")
        if not re.search(
            r'\bfiles\s*\[\s*\]\s*=\s*\{\s*"DayZSandbox_Expansion/scripts/4_World"\s*\}\s*;',
            world_body,
        ):
            violations.append(
                'E1: worldScriptModule debe tener files[] = {"DayZSandbox_Expansion/scripts/4_World"};'
            )
        mission_body = _find_class_body(defs_body, "missionScriptModule")
        if not re.search(
            r'\bfiles\s*\[\s*\]\s*=\s*\{\s*"DayZSandbox_Expansion/scripts/5_Mission"\s*\}\s*;',
            mission_body,
        ):
            violations.append(
                'E1: missionScriptModule debe tener files[] = {"DayZSandbox_Expansion/scripts/5_Mission"};'
            )

    return violations


def check_e2(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E2 guarda: cada .c del adaptador empieza por #ifdef EXPANSIONMODAI y acaba en #endif."""
    adapter_dir = Path(adapter_dir)
    if not adapter_dir.is_dir():
        return [f"E2: no existe el directorio {adapter_dir}"]

    c_files = sorted(adapter_dir.rglob("*.c"))
    if not c_files:
        return ["E2: no hay ficheros .c en el adaptador"]

    violations = []
    for p in c_files:
        rel = p.relative_to(adapter_dir).as_posix()
        code = _read_stripped(p)
        lines = [ln.strip() for ln in code.splitlines() if ln.strip()]
        if not lines:
            violations.append(f"E2: {rel} esta vacio tras quitar comentarios")
            continue
        if lines[0] != "#ifdef EXPANSIONMODAI":
            violations.append(
                f"E2: {rel}: la primera linea no vacia debe ser '#ifdef EXPANSIONMODAI', es '{lines[0]}'"
            )
        if lines[-1] != "#endif":
            violations.append(
                f"E2: {rel}: la ultima linea no vacia debe ser '#endif', es '{lines[-1]}'"
            )
        depth = 0
        closed_early = False
        for idx, ln in enumerate(lines):
            if re.match(r"#\s*(?:ifdef|ifndef|if)\b", ln):
                depth += 1
            elif re.match(r"#\s*endif\b", ln):
                depth -= 1
            if depth <= 0 and idx < len(lines) - 1:
                closed_early = True
                break
        if closed_early or depth != 0:
            violations.append(f"E2: {rel}: hay codigo fuera de la guarda #ifdef EXPANSIONMODAI")

    return violations


def check_e3(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E3 motor: class DSBX_ExpansionEngine : DSBX_ActorEngine, Name, IsAvailable y overrides."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E3: falta scripts/4_World/DSBX_ExpEngine.c"]

    code = _read_stripped(eng_path)
    violations = []
    if not re.search(r"\bclass\s+DSBX_ExpansionEngine\s*:\s*DSBX_ActorEngine\b", code):
        violations.append("E3: falta 'class DSBX_ExpansionEngine : DSBX_ActorEngine'")

    engine_body = _find_class_body(code, "DSBX_ExpansionEngine")
    if not engine_body:
        violations.append("E3: no se encontro el cuerpo de DSBX_ExpansionEngine")
        return violations

    name_body = _find_method_body(engine_body, "Name").strip()
    if name_body != 'return "expansion";':
        violations.append(f'E3: Name() debe devolver "expansion", tiene: {name_body!r}')

    avail_body = _find_method_body(engine_body, "IsAvailable").strip()
    if avail_body != "return true;":
        violations.append(f"E3: IsAvailable() debe devolver true, tiene: {avail_body!r}")

    for method_name, ret_type in EXPECTED_OVERRIDE_METHODS:
        if not re.search(
            rf"\boverride\s+{re.escape(ret_type)}\s+{re.escape(method_name)}\s*\(",
            engine_body,
        ):
            violations.append(f"E3: falta override {ret_type} {method_name}(...) en DSBX_ExpansionEngine")
        elif not _find_method_body(engine_body, method_name).strip():
            violations.append(f"E3: cuerpo vacio en DSBX_ExpansionEngine.{method_name}")

    return violations


def check_e4(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E4 registro: MissionServer registra el motor tras super.OnMissionStart() y llama a Tick."""
    adapter_dir = Path(adapter_dir)
    mis_path = adapter_dir / "scripts/5_Mission/DSBX_ExpMission.c"
    if not mis_path.is_file():
        return ["E4: falta scripts/5_Mission/DSBX_ExpMission.c"]

    code = _read_stripped(mis_path)
    violations = []
    if not re.search(r"\bmodded\s+class\s+MissionServer\b", code):
        violations.append("E4: falta 'modded class MissionServer'")

    ms_body = _find_class_body(code, "MissionServer")
    if not ms_body:
        violations.append("E4: falta cuerpo de MissionServer")
        return violations

    start_body = _find_method_body(ms_body, "OnMissionStart")
    if not start_body:
        violations.append("E4: falta OnMissionStart en MissionServer")
    else:
        super_pos = start_body.find("super.OnMissionStart();")
        reg_pos = start_body.find("DSBX_ActorEngineRegistry.Register(")
        if super_pos < 0:
            violations.append("E4: OnMissionStart no llama a super.OnMissionStart();")
        if reg_pos < 0:
            violations.append("E4: OnMissionStart no llama a DSBX_ActorEngineRegistry.Register(")
        if super_pos >= 0 and reg_pos >= 0 and reg_pos < super_pos:
            violations.append(
                "E4: DSBX_ActorEngineRegistry.Register( va antes de super.OnMissionStart();"
            )

    update_body = _find_method_body(ms_body, "OnUpdate")
    if not update_body:
        violations.append("E4: falta OnUpdate en MissionServer")
    else:
        if "super.OnUpdate(timeslice);" not in update_body:
            violations.append("E4: OnUpdate no llama a super.OnUpdate(timeslice);")
        if ".Tick(timeslice)" not in update_body:
            violations.append("E4: OnUpdate no llama a .Tick(timeslice)")

    return violations


def check_e5(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E5 alta: requisitos de Spawn en DSBX_ExpansionEngine (§4.1)."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E5: falta scripts/4_World/DSBX_ExpEngine.c"]

    code = _read_stripped(eng_path)
    engine_body = _find_class_body(code, "DSBX_ExpansionEngine")
    spawn_body = _find_method_body(engine_body, "Spawn")
    if not spawn_body:
        return ["E5: falta Spawn en DSBX_ExpansionEngine"]

    violations = []
    if not re.search(r'"eAI_"\s*\+', spawn_body):
        violations.append('E5: Spawn debe prefijar la clase con `"eAI_" +`')
    if "ConfigIsExisting" not in spawn_body:
        violations.append("E5: Spawn debe comprobar ConfigIsExisting")
    if "CreateObjectEx" not in spawn_body:
        violations.append("E5: Spawn debe crear el actor con CreateObjectEx")
    for flag in ("ECE_INITAI", "ECE_NOLIFETIME", "ECE_NOPERSISTENCY_WORLD"):
        if not re.search(rf"\b{flag}\b", spawn_body):
            violations.append(f"E5: falta el flag {flag} en Spawn")
    if not re.search(r"\beAIFactionPassive\b", spawn_body):
        violations.append("E5: falta eAIFactionPassive en Spawn")
    if "eAIGroup.CreateGroup(" not in spawn_body:
        violations.append("E5: falta eAIGroup.CreateGroup( en Spawn")
    if "SetGroup(" not in spawn_body:
        violations.append("E5: falta SetGroup( en Spawn")
    if "CreateAttachment(" not in spawn_body:
        violations.append("E5: falta CreateAttachment( en Spawn")

    return violations


def check_e6(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E6 prohibido: sin tokens vedados y toda llamada Expansion_SetEmote lleva false como 2o arg."""
    adapter_dir = Path(adapter_dir)
    if not adapter_dir.is_dir():
        return [f"E6: no existe el directorio {adapter_dir}"]

    c_files = sorted(adapter_dir.rglob("*.c"))
    if not c_files:
        return ["E6: no hay ficheros .c en el adaptador"]

    violations = []
    total_emote_calls = 0
    for p in c_files:
        rel = p.relative_to(adapter_dir).as_posix()
        code = _read_stripped(p)
        for tok in FORBIDDEN_ADAPTER_TOKENS:
            if tok in code:
                violations.append(f"E6: {rel} contiene token prohibido '{tok}'")
        for args in _extract_call_args(code, "Expansion_SetEmote"):
            total_emote_calls += 1
            if len(args) < 2 or args[1] != "false":
                violations.append(
                    f"E6: {rel}: Expansion_SetEmote({', '.join(args)}) debe llevar false como 2o argumento"
                )

    if total_emote_calls == 0:
        violations.append("E6: no se encontro ninguna llamada a Expansion_SetEmote(")

    return violations


def check_e7(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E7 gestos: pares exactos en EmoteId contra §5.1 y catalog-m1.json, return -1 y unknown_emote."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E7: falta scripts/4_World/DSBX_ExpEngine.c"]
    if not CATALOG_PATH.is_file():
        return [f"E7: falta el catalogo {CATALOG_PATH}"]

    catalog = json.loads(CATALOG_PATH.read_bytes().decode("utf-8"))
    catalog_emotes = catalog.get("emotes", [])

    code = _read_stripped(eng_path)
    engine_body = _find_class_body(code, "DSBX_ExpansionEngine")
    emote_body = _find_method_body(engine_body, "EmoteId") or _find_method_body(code, "EmoteId")
    if not emote_body:
        return ["E7: falta el metodo EmoteId"]

    violations = []
    pairs = re.findall(
        r'if\s*\(\s*emote\s*==\s*"([^"]*)"\s*\)\s*(?:\{\s*)?return\s+([\w.]+)\s*;(?:\s*\})?',
        emote_body,
    )
    if len(re.findall(r"\bif\s*\(", emote_body)) != len(pairs):
        violations.append("E7: EmoteId contiene ramas if con formato inesperado")
    if pairs != EXPECTED_EMOTE_PAIRS:
        violations.append(
            f"E7: los pares de EmoteId no coinciden con §5.1: actual={pairs}"
        )
    if [name for name, _ in pairs] != catalog_emotes:
        violations.append(
            f"E7: los nombres de EmoteId no coinciden con catalog-m1.json emotes: {[n for n, _ in pairs]}"
        )
    if not re.search(r"\breturn\s+-1\s*;\s*$", emote_body.strip()):
        violations.append("E7: EmoteId debe terminar en 'return -1;'")

    req_body = _find_method_body(engine_body, "RequestGesture")
    if '"unknown_emote"' not in req_body:
        violations.append('E7: RequestGesture debe devolver `"unknown_emote"`')

    return violations


def check_e8(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E8 nucleo: firmas de RequestGesture y Gestures en DSBX_ActorEngine, y uso en DSBX_ActorOps."""
    core_dir = Path(core_dir)
    ae_path = core_dir / "scripts/3_Game/DSBX_ActorEngine.c"
    ops_path = core_dir / "scripts/3_Game/DSBX_ActorOps.c"
    violations = []

    if not ae_path.is_file():
        violations.append("E8: falta DSBX_ActorEngine.c en el nucleo")
    else:
        ae_code = _read_stripped(ae_path)
        ae_body = _find_class_body(ae_code, "DSBX_ActorEngine")
        if not re.search(
            r"\bstring\s+RequestGesture\s*\(\s*string\s+lid\s*,\s*int\s+gi\s*,\s*string\s+emote\s*,\s*int\s+atMark\s*,\s*int\s+tMs\s*\)",
            ae_body,
        ):
            violations.append(
                "E8: DSBX_ActorEngine debe tener RequestGesture(string lid, int gi, string emote, int atMark, int tMs)"
            )
        if not re.search(r"\bstring\s+Gestures\s*\(\s*string\s+lid\s*\)", ae_body):
            violations.append("E8: DSBX_ActorEngine debe declarar string Gestures(string lid)")
        elif _find_method_body(ae_body, "Gestures").strip() != 'return "";':
            violations.append('E8: DSBX_ActorEngine.Gestures(string lid) debe tener cuerpo `return "";`')

    if not ops_path.is_file():
        violations.append("E8: falta DSBX_ActorOps.c en el nucleo")
    else:
        ops_code = _read_stripped(ops_path)
        ops_body = _find_class_body(ops_code, "DSBX_ActorOps")
        apply_body = _find_method_body(ops_body, "Apply")
        if not re.search(
            r"\bRequestGesture\s*\([^;]*\bargs\.g_at\s*\[\s*gi\s*\][^;]*\bargs\.g_t_ms\s*\[\s*gi\s*\]",
            apply_body,
        ):
            violations.append(
                "E8: DSBX_ActorOps.Apply debe pasar args.g_at[gi] y args.g_t_ms[gi] a RequestGesture"
            )
        read_body = _find_method_body(ops_body, "ReadJson")
        if "engine.Gestures(" not in read_body:
            violations.append("E8: DSBX_ActorOps.ReadJson debe llamar a engine.Gestures(")
        if '\\"gestures\\":[]' in read_body or '"gestures":[]' in read_body:
            violations.append("E8: DSBX_ActorOps.ReadJson no debe devolver gestures vacio fijo")

    return violations


def check_e9(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E9 eventos: causas en {timeout, interrupted, stop} y estados en los seis de F3-offline-1 §2.2."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E9: falta scripts/4_World/DSBX_ExpEngine.c"]

    code = _read_stripped(eng_path)
    literals = re.findall(r'"((?:\\.|[^"\\])*)"', code)
    lit_set = set(literals)
    violations = []

    for cause in sorted(VALID_CAUSES):
        if cause not in lit_set:
            violations.append(f'E9: falta la causa literal "{cause}" en el adaptador')

    for st in sorted(REQUIRED_EMITTED_STATES):
        if st not in lit_set:
            violations.append(f'E9: falta el estado de evento literal "{st}" en el adaptador')

    for assigned in re.findall(r'\b(?!\w*Json\b)\w*cause\w*\s*=\s*"([^"]+)"', code, flags=re.IGNORECASE):
        if assigned not in VALID_CAUSES:
            violations.append(f'E9: causa no permitida "{assigned}"')

    for pair_cause in re.findall(
        r'"(?:requested|playing|finished|canceled|rejected|expired)"\s*,\s*"([^"]+)"',
        code,
    ):
        if pair_cause not in VALID_CAUSES:
            violations.append(f'E9: causa no permitida "{pair_cause}"')

    for lit in literals:
        if not re.fullmatch(r"[A-Za-z_]+", lit):
            continue
        if lit in NON_EVENT_WORD_LITERALS:
            continue
        if lit in VALID_CAUSES or lit in VALID_EVENT_STATES:
            continue
        violations.append(f'E9: literal de estado o causa no permitido "{lit}"')

    return violations


ALL_CHECKS = {
    "E1": check_e1,
    "E2": check_e2,
    "E3": check_e3,
    "E4": check_e4,
    "E5": check_e5,
    "E6": check_e6,
    "E7": check_e7,
    "E8": check_e8,
    "E9": check_e9,
}


class TestExpAdapterStatic(unittest.TestCase):
    """Reglas estaticas E1-E9 sobre DayZSandbox_Expansion/ y DayZSandbox/."""

    def test_e1_forma(self):
        self.assertEqual(check_e1(ADAPTER_DIR, CORE_DIR), [])

    def test_e2_guarda(self):
        self.assertEqual(check_e2(ADAPTER_DIR, CORE_DIR), [])

    def test_e3_motor(self):
        self.assertEqual(check_e3(ADAPTER_DIR, CORE_DIR), [])

    def test_e4_registro(self):
        self.assertEqual(check_e4(ADAPTER_DIR, CORE_DIR), [])

    def test_e5_alta(self):
        self.assertEqual(check_e5(ADAPTER_DIR, CORE_DIR), [])

    def test_e6_prohibido(self):
        self.assertEqual(check_e6(ADAPTER_DIR, CORE_DIR), [])

    def test_e7_gestos(self):
        self.assertEqual(check_e7(ADAPTER_DIR, CORE_DIR), [])

    def test_e8_nucleo(self):
        self.assertEqual(check_e8(ADAPTER_DIR, CORE_DIR), [])

    def test_e9_eventos(self):
        self.assertEqual(check_e9(ADAPTER_DIR, CORE_DIR), [])


if __name__ == "__main__":
    unittest.main()
