"""Comprobacion estatica del adaptador DayZSandbox_Expansion/ (F3-adaptador §6 y §13.2, reglas E1-E12)."""

import json
import re
import unittest
from pathlib import Path

from app.tests.test_mod_static import _extract_block, _find_class_body, _find_method_body, _strip_comments

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
    ("Name", "string", ()),
    ("IsAvailable", "bool", ()),
    ("Spawn", "string", ("string", "string", "vector", "float", "array<string>")),
    ("SetMarks", "string", ("string", "array<vector>", "string", "float")),
    ("RequestGesture", "string", ("string", "int", "string", "int", "int")),
    ("State", "string", ("string",)),
    ("Stop", "string", ("string",)),
    ("Despawn", "string", ("string",)),
    ("Gestures", "string", ("string",)),
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

STATE_ROW_VARS = [
    "lidJson",
    "clsJson",
    "xJson",
    "yJson",
    "zJson",
    "yawJson",
    "itemsJson",
    "miJson",
    "stJson",
    "tJson",
]


def _read_stripped(path: Path) -> str:
    """Lee un fichero UTF-8 y elimina comentarios C/Enforce."""
    return _strip_comments(path.read_bytes().decode("utf-8", errors="replace"))


def _extract_call_args(code: str, func_name: str) -> list[list[str]]:
    """Extrae la lista de argumentos de cada llamada a func_name(...) (excluyendo su declaracion)."""
    calls = []
    for m in re.finditer(rf"\b{re.escape(func_name)}\s*\(", code):
        prefix = code[max(0, m.start() - 16) : m.start()]
        if re.search(r"\b(?:void|int|bool|float|string|override)\s+$", prefix):
            continue
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


def _param_types(params_str: str) -> tuple[str, ...]:
    """Devuelve la tupla de tipos de una lista de parametros Enforce."""
    s = params_str.strip()
    if not s:
        return ()
    out = []
    for part in s.split(","):
        tokens = part.strip().split()
        if len(tokens) < 2:
            out.append(part.strip())
        else:
            typ = " ".join(tokens[:-1])
            typ = re.sub(r"\s*([<>])\s*", r"\1", typ)
            out.append(typ)
    return tuple(out)


def check_e1(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E1 forma: arbol exacto de DayZSandbox_Expansion, $PBOPREFIX$, include.lst y config.cpp (N1)."""
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
    patches_body = _find_class_body(cfg, "CfgPatches")
    patches_exp = _find_class_body(patches_body, "DayZSandbox_Expansion") if patches_body else ""
    if not patches_exp:
        violations.append("E1: falta class CfgPatches -> class DayZSandbox_Expansion en config.cpp")
    else:
        m_req = re.search(r"\brequiredAddons\s*\[\s*\]\s*=\s*\{([^}]*)\}\s*;", patches_exp)
        if not m_req:
            violations.append("E1: falta requiredAddons[] en CfgPatches -> DayZSandbox_Expansion")
        else:
            items = [s.strip() for s in m_req.group(1).split(",") if s.strip()]
            if items != EXPECTED_REQUIRED_ADDONS:
                violations.append(
                    f"E1: requiredAddons distinto: actual={items} esperado={EXPECTED_REQUIRED_ADDONS}"
                )

    mods_body = _find_class_body(cfg, "CfgMods")
    mods_exp = _find_class_body(mods_body, "DayZSandbox_Expansion") if mods_body else ""
    if not mods_exp:
        violations.append("E1: falta class CfgMods -> class DayZSandbox_Expansion en config.cpp")
    else:
        m_dep = re.search(r"\bdependencies\s*\[\s*\]\s*=\s*\{([^}]*)\}\s*;", mods_exp)
        if not m_dep:
            violations.append("E1: falta dependencies[] en CfgMods -> DayZSandbox_Expansion")
        else:
            deps = [s.strip() for s in m_dep.group(1).split(",") if s.strip()]
            if deps != EXPECTED_DEPENDENCIES:
                violations.append(
                    f"E1: dependencies distinto: actual={deps} esperado={EXPECTED_DEPENDENCIES}"
                )

        defs_body = _find_class_body(mods_exp, "defs")
        if not defs_body:
            violations.append("E1: CfgMods -> DayZSandbox_Expansion no tiene class defs")
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
    """E2 guarda: cada .c empieza por #ifdef EXPANSIONMODAI, acaba en #endif y sin #else/#elif exterior (N2)."""
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
        outer_branch = False
        for idx, ln in enumerate(lines):
            if re.match(r"#\s*(?:ifdef|ifndef|if)\b", ln):
                depth += 1
            elif re.match(r"#\s*(?:else|elif)\b", ln):
                if depth == 1:
                    outer_branch = True
            elif re.match(r"#\s*endif\b", ln):
                depth -= 1
            if depth <= 0 and idx < len(lines) - 1:
                closed_early = True
                break
        if closed_early or depth != 0:
            violations.append(f"E2: {rel}: hay codigo fuera de la guarda #ifdef EXPANSIONMODAI")
        if outer_branch:
            violations.append(f"E2: {rel}: #else o #elif al nivel exterior de la guarda")

    return violations


def check_e3(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E3 motor: class DSBX_ExpansionEngine : DSBX_ActorEngine, Name, IsAvailable y firmas de override (N3)."""
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

    expected_map = {name: (ret, params) for name, ret, params in EXPECTED_OVERRIDE_METHODS}
    for method_name, ret_type, expected_params in EXPECTED_OVERRIDE_METHODS:
        m = re.search(
            rf"\boverride\s+([A-Za-z_][\w<>]*)\s+{re.escape(method_name)}\s*\(([^)]*)\)",
            engine_body,
        )
        if not m:
            violations.append(f"E3: falta override {ret_type} {method_name}(...) en DSBX_ExpansionEngine")
            continue
        actual_ret = m.group(1)
        actual_params = _param_types(m.group(2))
        if actual_ret != ret_type or actual_params != expected_params:
            violations.append(
                f"E3: firma de override {method_name} distinta a DSBX_ActorEngine: "
                f"actual=({actual_ret}, {actual_params}) esperado=({ret_type}, {expected_params})"
            )
        if not _find_method_body(engine_body, method_name).strip():
            violations.append(f"E3: cuerpo vacio en DSBX_ExpansionEngine.{method_name}")

    for m in re.finditer(r"\boverride\s+([A-Za-z_][\w<>]*)\s+(\w+)\s*\(([^)]*)\)", engine_body):
        mname = m.group(2)
        if mname not in expected_map:
            violations.append(f"E3: override {mname} no existe en DSBX_ActorEngine")

    return violations


def check_e4(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E4 registro: MissionServer instancia y registra m_DsbxExpEngine tras super y llama a Tick bajo if (N3)."""
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
        new_m = re.search(
            r"\bm_DsbxExpEngine\s*=\s*new\s+DSBX_ExpansionEngine\s*\(\s*\)\s*;",
            start_body,
        )
        reg_m = re.search(
            r"\bDSBX_ActorEngineRegistry\.Register\s*\(\s*m_DsbxExpEngine\s*\)\s*;",
            start_body,
        )
        if super_pos < 0:
            violations.append("E4: OnMissionStart no llama a super.OnMissionStart();")
        if not new_m:
            violations.append("E4: OnMissionStart debe hacer m_DsbxExpEngine = new DSBX_ExpansionEngine();")
        if not reg_m:
            violations.append(
                "E4: OnMissionStart debe llamar a DSBX_ActorEngineRegistry.Register(m_DsbxExpEngine);"
            )
        if super_pos >= 0 and new_m and reg_m:
            if not (super_pos < new_m.start() < reg_m.start()):
                violations.append(
                    "E4: OnMissionStart debe ejecutar super.OnMissionStart(), new DSBX_ExpansionEngine() y Register(m_DsbxExpEngine) en ese orden"
                )

    update_body = _find_method_body(ms_body, "OnUpdate")
    if not update_body:
        violations.append("E4: falta OnUpdate en MissionServer")
    else:
        super_up = update_body.find("super.OnUpdate(timeslice);")
        if super_up < 0:
            violations.append("E4: OnUpdate no llama a super.OnUpdate(timeslice);")
        if_m = re.search(r"\bif\s*\(\s*m_DsbxExpEngine\s*\)", update_body)
        if not if_m:
            violations.append("E4: OnUpdate debe comprobar if (m_DsbxExpEngine)")
        else:
            if super_up >= 0 and if_m.start() < super_up:
                violations.append("E4: if (m_DsbxExpEngine) debe ir despues de super.OnUpdate(timeslice);")
            brace_pos = update_body.find("{", if_m.end())
            if_block = _extract_block(update_body, brace_pos) if brace_pos >= 0 else update_body[if_m.end() :]
            if not re.search(r"\bm_DsbxExpEngine\.Tick\s*\(\s*timeslice\s*\)\s*;", if_block):
                violations.append(
                    "E4: OnUpdate debe llamar a m_DsbxExpEngine.Tick(timeslice) dentro de if (m_DsbxExpEngine)"
                )

    return violations


def check_e5(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E5 alta: requisitos de Spawn en DSBX_ExpansionEngine (§4.1 y N4)."""
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
    flags_m = re.search(
        r"\bint\s+flags\s*=\s*ECE_PLACE_ON_SURFACE\s*\|\s*ECE_INITAI\s*\|\s*ECE_NOLIFETIME\s*\|\s*ECE_NOPERSISTENCY_WORLD\s*;",
        spawn_body,
    )
    if not flags_m:
        violations.append(
            "E5: Spawn debe declarar int flags = ECE_PLACE_ON_SURFACE | ECE_INITAI | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD;"
        )
    create_calls = _extract_call_args(spawn_body, "CreateObjectEx")
    if not create_calls:
        violations.append("E5: Spawn debe crear el actor con CreateObjectEx")
    else:
        for args in create_calls:
            if len(args) != 3 or args[2] != "flags":
                violations.append(
                    f"E5: el tercer argumento de CreateObjectEx debe ser flags, es {args}"
                )
    if not re.search(r"\beAIFactionPassive\b", spawn_body):
        violations.append("E5: falta eAIFactionPassive en Spawn")
    if "eAIGroup.CreateGroup(" not in spawn_body:
        violations.append("E5: falta eAIGroup.CreateGroup( en Spawn")
    if "SetGroup(" not in spawn_body:
        violations.append("E5: falta SetGroup( en Spawn")
    sweep_m = re.search(r"\bSweepAttachments\s*\(\s*ai\s*\)\s*;", spawn_body)
    attach_pos = spawn_body.find("CreateAttachment(")
    if not sweep_m:
        violations.append("E5: falta SweepAttachments(ai); en Spawn")
    if attach_pos < 0:
        violations.append("E5: falta CreateAttachment( en Spawn")
    if sweep_m and attach_pos >= 0 and sweep_m.start() >= attach_pos:
        violations.append("E5: SweepAttachments(ai); debe ir antes del primer CreateAttachment(")

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
    """E7 gestos: cuerpo exacto de EmoteId contra §5.1 y catalog-m1.json, return -1 y unknown_emote (N7)."""
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
    if pairs != EXPECTED_EMOTE_PAIRS:
        violations.append(
            f"E7: los pares de EmoteId no coinciden con §5.1: actual={pairs}"
        )
    if [name for name, _ in pairs] != catalog_emotes:
        violations.append(
            f"E7: los nombres de EmoteId no coinciden con catalog-m1.json emotes: {[n for n, _ in pairs]}"
        )

    def _norm_emote_body(s: str) -> str:
        collapsed = re.sub(r"\s+", " ", s).strip()
        return re.sub(r"\s*([();]|==)\s*", r"\1", collapsed)

    expected_norm = (
        "".join(f'if(emote=="{name}")return {const};' for name, const in EXPECTED_EMOTE_PAIRS)
        + "return -1;"
    )
    if _norm_emote_body(emote_body) != expected_norm:
        violations.append("E7: el cuerpo de EmoteId debe ser exactamente el de §5.1 salvo espacios")

    req_body = _find_method_body(engine_body, "RequestGesture")
    if '"unknown_emote"' not in req_body:
        violations.append('E7: RequestGesture debe devolver `"unknown_emote"`')

    return violations


def check_e8(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E8 nucleo: firmas en DSBX_ActorEngine y llamadas exactas en DSBX_ActorOps (N8)."""
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
            r"\bengine\.RequestGesture\s*\(\s*args\.a_lid\s*,\s*gi\s*,\s*args\.g_emote\s*\[\s*gi\s*\]\s*,\s*args\.g_at\s*\[\s*gi\s*\]\s*,\s*args\.g_t_ms\s*\[\s*gi\s*\]\s*\)",
            apply_body,
        ):
            violations.append(
                "E8: DSBX_ActorOps.Apply debe llamar exactamente a engine.RequestGesture(args.a_lid, gi, args.g_emote[gi], args.g_at[gi], args.g_t_ms[gi])"
            )
        read_body = _find_method_body(ops_body, "ReadJson")
        m_loop = re.search(r"\bforeach\s*\(\s*string\s+lid\s*:\s*m_Lids\s*\)\s*\{", read_body)
        if not m_loop:
            violations.append("E8: DSBX_ActorOps.ReadJson debe recorrer m_Lids con foreach (string lid : m_Lids)")
        else:
            loop_body = _extract_block(read_body, read_body.find("{", m_loop.start()))
            row_add = re.search(r"\brows\s*=\s*rows\s*\+\s*row\s*;", loop_body)
            gest_call = re.search(r"\bengine\.Gestures\s*\(\s*lid\s*\)", loop_body)
            if not row_add or not gest_call or gest_call.start() <= row_add.start():
                violations.append(
                    "E8: DSBX_ActorOps.ReadJson debe llamar a engine.Gestures(lid) dentro del bucle, despues de anadir la fila"
                )
        if '\\"gestures\\":[]' in read_body or '"gestures":[]' in read_body:
            violations.append("E8: DSBX_ActorOps.ReadJson no debe devolver gestures vacio fijo")

    return violations


def check_e9(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E9 eventos: pares (estado, causa) en Emit/FinishGesture y reenvio en EmoteCB tras super (N9)."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E9: falta scripts/4_World/DSBX_ExpEngine.c"]

    code = _read_stripped(eng_path)
    violations = []

    no_cause_states = {"requested", "playing", "finished"}
    with_cause_states = {"canceled", "expired"}
    allowed_cause_args = {'"interrupted"', '"timeout"', '"stop"', "cause"}

    literal_calls = 0
    for fn_name in ("Emit", "FinishGesture"):
        for args in _extract_call_args(code, fn_name):
            if len(args) != 4:
                violations.append(f"E9: llamada a {fn_name} con {len(args)} argumentos: {args}")
                continue
            st_arg = args[2].strip()
            cause_arg = args[3].strip()
            if st_arg.startswith('"') and st_arg.endswith('"'):
                literal_calls += 1
                st_val = st_arg[1:-1]
                if st_val in no_cause_states:
                    if cause_arg != '""':
                        violations.append(
                            f'E9: {fn_name} con estado "{st_val}" debe llevar causa "", lleva {cause_arg}'
                        )
                elif st_val in with_cause_states:
                    if cause_arg not in allowed_cause_args:
                        violations.append(
                            f'E9: {fn_name} con estado "{st_val}" lleva causa no valida {cause_arg}'
                        )
                else:
                    violations.append(f'E9: {fn_name} con estado literal no valido "{st_val}"')

    if literal_calls == 0:
        violations.append("E9: no se encontraron llamadas a Emit o FinishGesture con estado literal")

    if not re.search(r"\bmodded\s+class\s+EmoteCB\b", code):
        violations.append("E9: falta modded class EmoteCB")
    else:
        cb_body = _find_class_body(code, "EmoteCB")
        osc_body = _find_method_body(cb_body, "OnStateChange")
        if not osc_body:
            violations.append("E9: falta OnStateChange en modded class EmoteCB")
        else:
            super_pos = osc_body.find("super.OnStateChange(")
            fwd_pos = osc_body.find(".OnState(")
            if super_pos < 0 or fwd_pos < 0 or super_pos >= fwd_pos:
                violations.append("E9: EmoteCB.OnStateChange debe reenviar a .OnState( tras super")

        of_body = _find_method_body(cb_body, "OnFinish")
        if not of_body:
            violations.append("E9: falta OnFinish en modded class EmoteCB")
        else:
            super_pos = of_body.find("super.OnFinish(")
            fwd_pos = of_body.find(".OnFinish(")
            if super_pos < 0 or fwd_pos < 0 or super_pos >= fwd_pos:
                violations.append("E9: EmoteCB.OnFinish debe reenviar a .OnFinish( tras super")

    return violations


def check_e10(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E10 movimiento: Tick llama a TickMarks, TickRoam y TickGestures; SetMarks y SendRoamDest (N5)."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E10: falta scripts/4_World/DSBX_ExpEngine.c"]

    code = _read_stripped(eng_path)
    engine_body = _find_class_body(code, "DSBX_ExpansionEngine")
    if not engine_body:
        return ["E10: falta DSBX_ExpansionEngine"]

    violations = []
    tick_body = _find_method_body(engine_body, "Tick")
    for call_pat, label in (
        (r"\bTickMarks\s*\(\s*rec\s*,\s*pos\s*\)\s*;", "TickMarks(rec, pos);"),
        (r"\bTickRoam\s*\(\s*rec\s*,\s*pos\s*\)\s*;", "TickRoam(rec, pos);"),
        (r"\bTickGestures\s*\(\s*rec\s*\)\s*;", "TickGestures(rec);"),
    ):
        if not re.search(call_pat, tick_body):
            violations.append(f"E10: Tick debe llamar a {label}")

    set_marks_body = _find_method_body(engine_body, "SetMarks")
    if not re.search(
        r'if\s*\(\s*behaviour\s*==\s*"ONCE"\s*\)\s*\{\s*group\.SetWaypointBehaviour\s*\(\s*eAIWaypointBehavior\.ONCE\s*\)\s*;\s*\}\s*else\s*\{\s*group\.SetWaypointBehaviour\s*\(\s*eAIWaypointBehavior\.LOOP\s*\)\s*;\s*\}',
        set_marks_body,
    ):
        violations.append(
            "E10: SetMarks debe usar eAIWaypointBehavior.ONCE en la rama ONCE y eAIWaypointBehavior.LOOP en la otra"
        )

    roam_body = _find_method_body(engine_body, "SendRoamDest")
    if not re.search(r"\b0\.35\s*\+\s*0\.4\s*\*", roam_body):
        violations.append("E10: SendRoamDest debe usar 0.35 + 0.4 *")
    if not re.search(r"\brec\.m_Roam\s*\*\s*frac\b", roam_body):
        violations.append("E10: SendRoamDest debe usar rec.m_Roam * frac")

    return violations


def check_e11(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E11 fila: orden exacto de las 10 columnas y fila de muerto en State (N10)."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E11: falta scripts/4_World/DSBX_ExpEngine.c"]

    code = _read_stripped(eng_path)
    engine_body = _find_class_body(code, "DSBX_ExpansionEngine")
    state_body = _find_method_body(engine_body, "State")
    if not state_body:
        return ["E11: falta State en DSBX_ExpansionEngine"]

    violations = []
    if not re.search(
        r'"\["\s*\+\s*lidJson\s*\+\s*",null,null,null,null,null,\[\],-1,\\"idle\\","\s*\+\s*tJson\s*\+\s*"\]"',
        state_body,
    ):
        violations.append(
            'E11: la fila de muerto en State debe ser "[" + lidJson + ",null,null,null,null,null,[],-1,\\"idle\\"," + tJson + "]"'
        )

    row_start = state_body.find("string row")
    if row_start < 0:
        violations.append("E11: falta el armado de la fila en State")
    else:
        row_section = state_body[row_start:]
        found_vars = re.findall(
            r"\b(?:lidJson|clsJson|xJson|yJson|zJson|yawJson|itemsJson|miJson|stJson|tJson)\b",
            row_section,
        )
        if found_vars != STATE_ROW_VARS:
            violations.append(
                f"E11: orden de columnas en State distinto: actual={found_vars} esperado={STATE_ROW_VARS}"
            )

    return violations


def check_e12(adapter_dir: Path, core_dir: Path) -> list[str]:
    """E12 parada: Stop fija HOLD antes de CancelActive; Despawn cancela, borra entidad y quita del mapa (N11)."""
    adapter_dir = Path(adapter_dir)
    eng_path = adapter_dir / "scripts/4_World/DSBX_ExpEngine.c"
    if not eng_path.is_file():
        return ["E12: falta scripts/4_World/DSBX_ExpEngine.c"]

    code = _read_stripped(eng_path)
    engine_body = _find_class_body(code, "DSBX_ExpansionEngine")
    if not engine_body:
        return ["E12: falta DSBX_ExpansionEngine"]

    violations = []
    stop_body = _find_method_body(engine_body, "Stop")
    if not stop_body:
        violations.append("E12: falta Stop en DSBX_ExpansionEngine")
    else:
        m_hold = re.search(r'\brec\.m_Behaviour\s*=\s*"HOLD"\s*;', stop_body)
        m_cancel = re.search(r'\bCancelActive\s*\(\s*rec\s*,\s*"stop"\s*\)\s*;', stop_body)
        if not m_hold:
            violations.append('E12: Stop debe contener rec.m_Behaviour = "HOLD";')
        if not m_cancel:
            violations.append('E12: Stop debe contener CancelActive(rec, "stop");')
        if m_hold and m_cancel and m_hold.start() >= m_cancel.start():
            violations.append('E12: en Stop, rec.m_Behaviour = "HOLD"; debe ir antes de CancelActive(rec, "stop");')

    despawn_body = _find_method_body(engine_body, "Despawn")
    if not despawn_body:
        violations.append("E12: falta Despawn en DSBX_ExpansionEngine")
    else:
        if not re.search(r'\bCancelActive\s*\(\s*rec\s*,\s*"stop"\s*\)\s*;', despawn_body):
            violations.append('E12: Despawn debe contener CancelActive(rec, "stop");')
        if not re.search(r"\bg_Game\.ObjectDelete\s*\(\s*rec\.m_Ai\s*\)\s*;", despawn_body):
            violations.append("E12: Despawn debe contener g_Game.ObjectDelete(rec.m_Ai);")
        if not re.search(r"\bm_Actors\.Remove\s*\(\s*lid\s*\)\s*;", despawn_body):
            violations.append("E12: Despawn debe contener m_Actors.Remove(lid);")

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
    "E10": check_e10,
    "E11": check_e11,
    "E12": check_e12,
}


class TestExpAdapterStatic(unittest.TestCase):
    """Reglas estaticas E1-E12 sobre DayZSandbox_Expansion/ y DayZSandbox/."""

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

    def test_e10_movimiento(self):
        self.assertEqual(check_e10(ADAPTER_DIR, CORE_DIR), [])

    def test_e11_fila(self):
        self.assertEqual(check_e11(ADAPTER_DIR, CORE_DIR), [])

    def test_e12_parada(self):
        self.assertEqual(check_e12(ADAPTER_DIR, CORE_DIR), [])


if __name__ == "__main__":
    unittest.main()
