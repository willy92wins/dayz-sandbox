"""Prueba estatica de la sonda QA en Enforce (brief F0.2 §6.2)."""

import re
import tempfile
import unittest
from pathlib import Path

QA_DIR = Path(__file__).resolve().parents[1]
REAL_PROBE_DIR = QA_DIR / "probe" / "DayZSandbox_QA"

EXPECTED_REL_FILES = (
    "$PBOPREFIX$",
    "include.lst",
    "config.cpp",
    "scripts/5_Mission/DSBX_QA_Messages.c",
    "scripts/5_Mission/DSBX_QA_Probe.c",
    "scripts/5_Mission/DSBX_QA_Mission.c",
)

EXPECTED_C_FILES = (
    "scripts/5_Mission/DSBX_QA_Messages.c",
    "scripts/5_Mission/DSBX_QA_Probe.c",
    "scripts/5_Mission/DSBX_QA_Mission.c",
)

EXPECTED_JSON_CLASSES = {
    "DSBX_QA_Config": [
        ("string", "url"),
        ("string", "key"),
        ("int", "retry_ms"),
    ],
    "DSBX_QA_HelloResp": [
        ("int", "lease_ms"),
    ],
    "DSBX_QA_PollResp": [
        ("float", "now_ms"),
        ("ref array<ref DSBX_QA_Op>", "ops"),
    ],
    "DSBX_QA_Op": [
        ("string", "op_id"),
        ("string", "verb"),
        ("string", "inst"),
        ("float", "issued_ms"),
        ("int", "ttl_ms"),
        ("ref DSBX_QA_Args", "args"),
    ],
    "DSBX_QA_Args": [
        ("float", "x"),
        ("float", "z"),
        ("float", "fog"),
        ("ref array<float>", "pos"),
        ("ref array<float>", "ypr"),
        ("int", "count"),
        ("int", "interval_ms"),
        ("int", "seq0"),
        ("string", "client_inst"),
    ],
    "DSBX_QA_Result": [
        ("string", "op_id"),
        ("string", "status"),
        ("string", "reason"),
        ("int", "dup"),
        ("float", "recv_ms"),
        ("float", "done_ms"),
        ("int", "frame_recv"),
        ("int", "frame_done"),
        ("ref DSBX_QA_Read", "read"),
    ],
    "DSBX_QA_Read": [
        ("ref array<string>", "has"),
        ("int", "frame"),
        ("float", "tick_s"),
        ("float", "y"),
        ("float", "fog"),
        ("ref array<float>", "pos"),
        ("ref array<float>", "ypr"),
        ("ref array<ref DSBX_QA_RpcEntry>", "rpc_log"),
    ],
    "DSBX_QA_RpcEntry": [
        ("int", "seq"),
        ("float", "recv_ms"),
        ("float", "lease_age_ms"),
        ("string", "decision"),
    ],
}

WRITE_JSON_CLASSES = (
    "DSBX_QA_Result",
    "DSBX_QA_Read",
    "DSBX_QA_RpcEntry",
)

FORBIDDEN_C_TOKENS = (
    "GET_now",
    "POST_now",
    "FILE_now",
    ".FILE(",
    ".reset(",
    "EnableDebug",
    "DebugList",
    "JsonLoadFile",
    "GetCurrentCamera",
)

HELLO_BODY_TOKENS = (
    r'\"proto\":\"qa0\"',
    r'\"peer\":\"',
    r'\"inst\":\"',
    r'\"build\":\"',
    r'\"probe_ver\":\"dsbx-qa0\"',
)

DUP_CONVERSION_LITERALS = (
    r'\"dup\":0',
    r'\"dup\":1',
    r'\"dup\":false',
    r'\"dup\":true',
)


def _strip_comments(text, blank_strings=False):
    """Elimina comentarios // y /* */ conservando longitudes y saltos de linea."""
    out = list(text)
    n = len(text)
    i = 0
    state = "code"
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == '"':
                state = "string"
                i += 1
            elif ch == "/" and nxt == "/":
                out[i] = " "
                out[i + 1] = " "
                state = "line_comment"
                i += 2
            elif ch == "/" and nxt == "*":
                out[i] = " "
                out[i + 1] = " "
                state = "block_comment"
                i += 2
            else:
                i += 1
        elif state == "string":
            if ch == "\\" and i + 1 < n:
                if blank_strings:
                    out[i] = " "
                    if text[i + 1] != "\n":
                        out[i + 1] = " "
                i += 2
            elif ch == '"':
                state = "code"
                i += 1
            else:
                if blank_strings and ch != "\n":
                    out[i] = " "
                i += 1
        elif state == "line_comment":
            if ch == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                out[i] = " "
                out[i + 1] = " "
                state = "code"
                i += 2
            else:
                if ch != "\n":
                    out[i] = " "
                i += 1
    return "".join(out)


def _find_matching_brace(code_no_strings, open_idx):
    depth = 0
    for idx in range(open_idx, len(code_no_strings)):
        ch = code_no_strings[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _find_matching_paren(code_no_strings, open_idx):
    depth = 0
    for idx in range(open_idx, len(code_no_strings)):
        ch = code_no_strings[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _normalize_type(raw_type):
    norm = re.sub(r"\s+", " ", raw_type.strip())
    norm = re.sub(r"\s*<\s*", "<", norm)
    norm = re.sub(r"\s*>\s*", ">", norm)
    return norm


def _extract_named_blocks(code_no_strings, keyword="class"):
    """Devuelve lista de (name, header_start, body_start, body_end) en el nivel superior del texto dado."""
    pattern = re.compile(
        rf"\b{keyword}\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*(?::|extends)\s*[A-Za-z_][A-Za-z0-9_]*)?\s*\{{",
        re.MULTILINE,
    )
    blocks = []
    pos = 0
    while pos < len(code_no_strings):
        m = pattern.search(code_no_strings, pos)
        if not m:
            break
        open_brace = m.end() - 1
        close_brace = _find_matching_brace(code_no_strings, open_brace)
        if close_brace == -1:
            break
        blocks.append((m.group(1), m.start(), open_brace + 1, close_brace))
        pos = close_brace + 1
    return blocks


def _extract_classes_and_members(messages_text):
    """Extrae las clases de DSBX_QA_Messages.c, sus miembros y constructores."""
    code_with_strings = _strip_comments(messages_text, blank_strings=False)
    code_no_strings = _strip_comments(messages_text, blank_strings=True)
    raw_blocks = _extract_named_blocks(code_no_strings, keyword="class")
    parsed = []
    method_re = re.compile(
        r"\b(?:void|bool|string|int|float)\s+(~?[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{",
        re.MULTILINE,
    )
    for class_name, hdr_start, body_start, body_end in raw_blocks:
        body_no_str = code_no_strings[body_start:body_end]
        body_with_str = code_with_strings[body_start:body_end]
        methods = []
        masked = list(body_with_str)
        mpos = 0
        while mpos < len(body_no_str):
            mm = method_re.search(body_no_str, mpos)
            if not mm:
                break
            m_open = mm.end() - 1
            m_close = _find_matching_brace(body_no_str, m_open)
            if m_close == -1:
                break
            methods.append(
                (
                    mm.group(1),
                    body_with_str[m_open + 1 : m_close],
                    body_no_str[m_open + 1 : m_close],
                )
            )
            end_mask = m_close + 1
            while end_mask < len(body_no_str) and body_no_str[end_mask] in " \t;":
                end_mask += 1
            for k in range(mm.start(), end_mask):
                if masked[k] != "\n":
                    masked[k] = " "
            mpos = end_mask
        member_lines = [
            (line_idx + 1, line.strip())
            for line_idx, line in enumerate("".join(masked).splitlines())
            if line.strip()
        ]
        parsed.append(
            {
                "name": class_name,
                "header_start": hdr_start,
                "member_lines": member_lines,
                "methods": methods,
            }
        )
    return parsed


def _iter_c_files(probe_dir):
    probe_dir = Path(probe_dir)
    found = []
    for rel in EXPECTED_C_FILES:
        p = probe_dir / rel
        if p.is_file():
            found.append((rel, p))
    for p in sorted(probe_dir.rglob("*.c")):
        rel = p.relative_to(probe_dir).as_posix()
        if all(r != rel for r, _ in found):
            found.append((rel, p))
    return found


def _find_methods_in_c(code_no_strings, method_name):
    """Devuelve lista de dicts con header_span, body_span, full_span para method_name."""
    pattern = re.compile(
        rf"\b(?:(?:protected|private|override|static)\s+)*(?:void|bool|string|int|float)\s+{re.escape(method_name)}\s*\([^)]*\)\s*\{{",
        re.MULTILINE,
    )
    results = []
    pos = 0
    while pos < len(code_no_strings):
        m = pattern.search(code_no_strings, pos)
        if not m:
            break
        open_brace = m.end() - 1
        close_brace = _find_matching_brace(code_no_strings, open_brace)
        if close_brace == -1:
            break
        results.append(
            {
                "header_span": (m.start(), open_brace),
                "body_span": (open_brace + 1, close_brace),
                "full_span": (m.start(), close_brace + 1),
            }
        )
        pos = close_brace + 1
    return results


def _line_no(text, offset):
    return text.count("\n", 0, offset) + 1


# ---------------------------------------------------------------------------
# Las 8 comprobaciones de §6.2
# ---------------------------------------------------------------------------


def check_1_mod_files(probe_dir):
    """§6.2(1): $PBOPREFIX$, include.lst y config.cpp estan como en §4.1 (y los 3 .c en 5_Mission)."""
    probe_dir = Path(probe_dir)
    violations = []

    pbo_prefix = probe_dir / "$PBOPREFIX$"
    if not pbo_prefix.is_file():
        violations.append("$PBOPREFIX$: fichero ausente")
    else:
        text = pbo_prefix.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) != 1 or lines[0].strip() != "DayZSandbox_QA":
            violations.append(f"$PBOPREFIX$: se esperaba una linea 'DayZSandbox_QA', recibido {lines!r}")

    include_lst = probe_dir / "include.lst"
    if not include_lst.is_file():
        violations.append("include.lst: fichero ausente")
    else:
        text = include_lst.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) != 1 or lines[0].strip() != "*.c":
            violations.append(f"include.lst: se esperaba una linea '*.c', recibido {lines!r}")

    config_cpp = probe_dir / "config.cpp"
    if not config_cpp.is_file():
        violations.append("config.cpp: fichero ausente")
    else:
        raw_cfg = config_cpp.read_text(encoding="utf-8", errors="replace")
        cfg_clean = _strip_comments(raw_cfg, blank_strings=False)
        cfg_no_str = _strip_comments(raw_cfg, blank_strings=True)
        top_blocks = {name: (bs, be) for name, _, bs, be in _extract_named_blocks(cfg_no_str, "class")}

        if "CfgPatches" not in top_blocks:
            violations.append("config.cpp: falta class CfgPatches")
        else:
            bs, be = top_blocks["CfgPatches"]
            patches_sub = {
                name: (sbs, sbe)
                for name, _, sbs, sbe in _extract_named_blocks(cfg_no_str[bs:be], "class")
            }
            if "DayZSandbox_QA" not in patches_sub:
                violations.append("config.cpp: falta class DayZSandbox_QA dentro de CfgPatches")
            else:
                sbs, sbe = patches_sub["DayZSandbox_QA"]
                patch_body = cfg_clean[bs + sbs : bs + sbe]
                for desc, pat in (
                    ("units[] = {}", r"\bunits\s*\[\s*\]\s*=\s*\{\s*\}\s*;"),
                    ("weapons[] = {}", r"\bweapons\s*\[\s*\]\s*=\s*\{\s*\}\s*;"),
                    ("requiredVersion = 0.1", r"\brequiredVersion\s*=\s*0\.1\s*;"),
                    ('requiredAddons[] = {"DZ_Data"}', r'\brequiredAddons\s*\[\s*\]\s*=\s*\{\s*"DZ_Data"\s*\}\s*;'),
                ):
                    if not re.search(pat, patch_body, re.DOTALL):
                        violations.append(f"config.cpp: CfgPatches::DayZSandbox_QA sin {desc}")

        if "CfgMods" not in top_blocks:
            violations.append("config.cpp: falta class CfgMods")
        else:
            bs, be = top_blocks["CfgMods"]
            mods_sub = {
                name: (sbs, sbe)
                for name, _, sbs, sbe in _extract_named_blocks(cfg_no_str[bs:be], "class")
            }
            if "DayZSandbox_QA" not in mods_sub:
                violations.append("config.cpp: falta class DayZSandbox_QA dentro de CfgMods")
            else:
                sbs, sbe = mods_sub["DayZSandbox_QA"]
                mod_body = cfg_clean[bs + sbs : bs + sbe]
                mod_no_str = cfg_no_str[bs + sbs : bs + sbe]
                for desc, pat in (
                    ('dir = "DayZSandbox_QA"', r'\bdir\s*=\s*"DayZSandbox_QA"\s*;'),
                    ('name = "DayZSandbox_QA"', r'\bname\s*=\s*"DayZSandbox_QA"\s*;'),
                    ('type = "mod"', r'\btype\s*=\s*"mod"\s*;'),
                    ('dependencies[] = {"Mission"}', r'\bdependencies\s*\[\s*\]\s*=\s*\{\s*"Mission"\s*\}\s*;'),
                ):
                    if not re.search(pat, mod_body, re.DOTALL):
                        violations.append(f"config.cpp: CfgMods::DayZSandbox_QA sin {desc}")

                defs_sub = {
                    name: (dbs, dbe)
                    for name, _, dbs, dbe in _extract_named_blocks(mod_no_str, "class")
                }
                if "defs" not in defs_sub:
                    violations.append("config.cpp: falta class defs dentro de CfgMods::DayZSandbox_QA")
                else:
                    dbs, dbe = defs_sub["defs"]
                    defs_no_str = mod_no_str[dbs:dbe]
                    defs_clean = mod_body[dbs:dbe]
                    modules = {
                        name: (mbs, mbe)
                        for name, _, mbs, mbe in _extract_named_blocks(defs_no_str, "class")
                    }
                    if set(modules.keys()) != {"missionScriptModule"}:
                        violations.append(
                            f"config.cpp: defs debe tener solo missionScriptModule, tiene {sorted(modules.keys())}"
                        )
                    if "missionScriptModule" in modules:
                        mbs, mbe = modules["missionScriptModule"]
                        m_body = defs_clean[mbs:mbe]
                        if not re.search(r'\bvalue\s*=\s*""\s*;', m_body, re.DOTALL):
                            violations.append('config.cpp: missionScriptModule sin value = ""')
                        if not re.search(
                            r'\bfiles\s*\[\s*\]\s*=\s*\{\s*"DayZSandbox_QA/scripts/5_Mission"\s*\}\s*;',
                            m_body,
                            re.DOTALL,
                        ):
                            violations.append(
                                'config.cpp: missionScriptModule sin files[] = {"DayZSandbox_QA/scripts/5_Mission"}'
                            )

    for rel in EXPECTED_C_FILES:
        if not (probe_dir / rel).is_file():
            violations.append(f"{rel}: fichero ausente")

    all_c = sorted(p.relative_to(probe_dir).as_posix() for p in probe_dir.rglob("*.c"))
    for rel in all_c:
        if rel not in EXPECTED_C_FILES:
            violations.append(f"{rel}: fichero .c fuera de los tres de §2")

    return violations


def check_2_json_classes(probe_dir):
    """§6.2(2): DSBX_QA_Messages.c tiene exactamente las 8 clases de §4.5 con sus miembros exactos."""
    probe_dir = Path(probe_dir)
    msg_path = probe_dir / "scripts/5_Mission/DSBX_QA_Messages.c"
    if not msg_path.is_file():
        return ["scripts/5_Mission/DSBX_QA_Messages.c: fichero ausente"]

    text = msg_path.read_text(encoding="utf-8", errors="replace")
    classes = _extract_classes_and_members(text)
    violations = []

    found_names = [c["name"] for c in classes]
    expected_names = list(EXPECTED_JSON_CLASSES.keys())

    if len(found_names) != len(set(found_names)):
        violations.append(f"DSBX_QA_Messages.c: clases duplicadas en {found_names}")

    missing_classes = [c for c in expected_names if c not in found_names]
    extra_classes = [c for c in found_names if c not in EXPECTED_JSON_CLASSES]
    for c in missing_classes:
        violations.append(f"DSBX_QA_Messages.c: falta la clase {c}")
    for c in extra_classes:
        violations.append(f"DSBX_QA_Messages.c: clase de mas {c}")

    modifier_re = re.compile(r"\b(protected|private|static|const|autoptr)\b")
    member_decl_re = re.compile(r"^(.+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;$")

    for cls_info in classes:
        cname = cls_info["name"]
        if cname not in EXPECTED_JSON_CLASSES:
            continue
        expected_members = EXPECTED_JSON_CLASSES[cname]
        actual_members = []
        for rel_line, line in cls_info["member_lines"]:
            if line.count(";") != 1:
                violations.append(
                    f"DSBX_QA_Messages.c:{cname}:linea {rel_line}: debe ir un miembro por linea con ';': {line!r}"
                )
                continue
            if "=" in line:
                violations.append(
                    f"DSBX_QA_Messages.c:{cname}:linea {rel_line}: miembro con valor inicial no permitido: {line!r}"
                )
                continue
            mod_m = modifier_re.search(line)
            if mod_m:
                violations.append(
                    f"DSBX_QA_Messages.c:{cname}:linea {rel_line}: modificador {mod_m.group(1)!r} no permitido: {line!r}"
                )
                continue
            decl_m = member_decl_re.match(line)
            if not decl_m:
                violations.append(
                    f"DSBX_QA_Messages.c:{cname}:linea {rel_line}: declaracion de miembro invalida: {line!r}"
                )
                continue
            m_type = _normalize_type(decl_m.group(1))
            m_name = decl_m.group(2)
            actual_members.append((m_type, m_name))

        for exp in expected_members:
            if exp not in actual_members:
                violations.append(
                    f"DSBX_QA_Messages.c:{cname}: falta el miembro '{exp[0]} {exp[1]}'"
                )
        for act in actual_members:
            if act not in expected_members:
                violations.append(
                    f"DSBX_QA_Messages.c:{cname}: miembro de mas o renombrado '{act[0]} {act[1]}'"
                )
        if len(actual_members) != len(set(actual_members)):
            violations.append(f"DSBX_QA_Messages.c:{cname}: miembros repetidos {actual_members}")

    return violations


def check_3_write_ctors(probe_dir):
    """§6.2(3): En las clases que se escriben, el constructor crea cada miembro ref."""
    probe_dir = Path(probe_dir)
    msg_path = probe_dir / "scripts/5_Mission/DSBX_QA_Messages.c"
    if not msg_path.is_file():
        return ["scripts/5_Mission/DSBX_QA_Messages.c: fichero ausente"]

    text = msg_path.read_text(encoding="utf-8", errors="replace")
    classes = {c["name"]: c for c in _extract_classes_and_members(text)}
    violations = []

    member_decl_re = re.compile(r"^(.+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;$")

    for cname in WRITE_JSON_CLASSES:
        if cname not in classes:
            violations.append(f"DSBX_QA_Messages.c: falta la clase de escritura {cname}")
            continue
        cls_info = classes[cname]
        ref_members = []
        for m_type, m_name in EXPECTED_JSON_CLASSES[cname]:
            if m_type.startswith("ref "):
                ref_members.append((_normalize_type(m_type[4:]), m_name))
        for _, line in cls_info["member_lines"]:
            dm = member_decl_re.match(line)
            if dm:
                m_type = _normalize_type(dm.group(1))
                m_name = dm.group(2)
                if m_type.startswith("ref "):
                    pair = (_normalize_type(m_type[4:]), m_name)
                    if pair not in ref_members:
                        ref_members.append(pair)

        if not ref_members:
            continue

        ctors = [body_no_str for mname, _, body_no_str in cls_info["methods"] if mname == cname]
        if not ctors:
            violations.append(f"DSBX_QA_Messages.c:{cname}: falta el constructor void {cname}()")
            continue

        ctor_norm = _normalize_type(" ".join(ctors))
        for target_type, member_name in ref_members:
            new_pat = re.compile(
                rf"(?:this\s*\.\s*)?(?<![A-Za-z0-9_]){re.escape(member_name)}\s*=\s*new\s+(?:ref\s+)?{re.escape(target_type)}(?:\s*\(\s*\))?\s*;"
            )
            if not new_pat.search(ctor_norm):
                violations.append(
                    f"DSBX_QA_Messages.c:{cname}: el constructor no crea el miembro ref '{member_name}' con 'new {target_type}'"
                )

    return violations


def check_4_forbidden_tokens(probe_dir):
    """§6.2(4): Ningun .c contiene GET_now, POST_now, FILE_now, .FILE(, .reset(, EnableDebug, DebugList, JsonLoadFile ni GetCurrentCamera."""
    violations = []
    patterns = [
        ("GET_now", re.compile(r"(?<![A-Za-z0-9_])GET_now(?![A-Za-z0-9_])")),
        ("POST_now", re.compile(r"(?<![A-Za-z0-9_])POST_now(?![A-Za-z0-9_])")),
        ("FILE_now", re.compile(r"(?<![A-Za-z0-9_])FILE_now(?![A-Za-z0-9_])")),
        (".FILE(", re.compile(r"\.\s*FILE\s*\(")),
        (".reset(", re.compile(r"\.\s*reset\s*\(")),
        ("EnableDebug", re.compile(r"(?<![A-Za-z0-9_])EnableDebug(?![A-Za-z0-9_])")),
        ("DebugList", re.compile(r"(?<![A-Za-z0-9_])DebugList(?![A-Za-z0-9_])")),
        ("JsonLoadFile", re.compile(r"(?<![A-Za-z0-9_])JsonLoadFile(?![A-Za-z0-9_])")),
        ("GetCurrentCamera", re.compile(r"(?<![A-Za-z0-9_])GetCurrentCamera(?![A-Za-z0-9_])")),
    ]
    for rel, path in _iter_c_files(probe_dir):
        text = path.read_text(encoding="utf-8", errors="replace")
        clean = _strip_comments(text, blank_strings=False)
        for label, pat in patterns:
            for m in pat.finditer(clean):
                lineno = _line_no(clean, m.start())
                violations.append(f"{rel}:{lineno}: contiene API prohibida {label!r}")
    return violations


def check_5_key_containment(probe_dir):
    """§6.2(5): La clave esta contenida (Log, m_Key, .key, literales en LoadConfig, KeyQuery en GET/POST, err de LoadFile)."""
    violations = []
    c_files = _iter_c_files(probe_dir)
    if not c_files:
        return ["No se encontraron ficheros .c en la sonda"]

    print_debug_re = re.compile(
        r"(?<![A-Za-z0-9_])(?:Print|PrintFormat|PrintToRPT|Error|ErrorEx|DPrint)\s*\(|(?<![A-Za-z0-9_])Debug\s*\."
    )
    m_key_re = re.compile(r"(?<![A-Za-z0-9_])m_Key(?![A-Za-z0-9_])")
    dot_key_re = re.compile(r"\.\s*key(?![A-Za-z0-9_])")
    log_call_re = re.compile(r"(?<![A-Za-z0-9_])Log\s*\(")
    key_query_re = re.compile(r"(?<![A-Za-z0-9_])KeyQuery\s*\(")
    get_or_post_re = re.compile(r"\.\s*(?:GET|POST)\s*\(")
    loadfile_re = re.compile(r"\bLoadFile\s*\(")
    string_literal_re = re.compile(r'^"(?:\\.|[^"\\])*"$')

    total_log_defs = 0
    total_loadconfig_defs = 0
    total_keyquery_defs = 0
    total_m_key_decls = 0
    total_dot_key = 0
    total_keyquery_calls = 0
    total_loadfile_calls = 0

    for rel, path in c_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        code_with_str = _strip_comments(text, blank_strings=False)
        code_no_str = _strip_comments(text, blank_strings=True)
        lines_no_str = code_no_str.splitlines()
        lines_with_str = code_with_str.splitlines()

        log_defs = _find_methods_in_c(code_no_str, "Log")
        loadconfig_defs = _find_methods_in_c(code_no_str, "LoadConfig")
        keyquery_defs = _find_methods_in_c(code_no_str, "KeyQuery")

        total_log_defs += len(log_defs)
        total_loadconfig_defs += len(loadconfig_defs)
        total_keyquery_defs += len(keyquery_defs)

        probe_class_spans = [
            (bs, be)
            for cname, _, bs, be in _extract_named_blocks(code_no_str, "class")
            if cname == "DSBX_QA_Probe"
        ]

        def _in_spans(offset, spans):
            return any(s <= offset < e for s, e in spans)

        def _is_at_probe_class_member_scope(offset):
            for bs, be in probe_class_spans:
                if bs <= offset < be:
                    sub = code_no_str[bs:offset]
                    if sub.count("{") - sub.count("}") == 0:
                        return True
            return False

        log_body_spans = [d["body_span"] for d in log_defs]
        loadconfig_body_spans = [d["body_span"] for d in loadconfig_defs]
        keyquery_body_spans = [d["body_span"] for d in keyquery_defs]
        keyquery_header_spans = [d["header_span"] for d in keyquery_defs]

        # 5a: Print/PrintFormat/PrintToRPT/Error/ErrorEx/DPrint/Debug. solo dentro de Log()
        for m in print_debug_re.finditer(code_no_str):
            if not _in_spans(m.start(), log_body_spans):
                lineno = _line_no(code_no_str, m.start())
                violations.append(
                    f"{rel}:{lineno}: llamada {m.group(0).strip()!r} fuera de Log()"
                )

        # 5b: m_Key solo en su declaracion, en LoadConfig() y en KeyQuery()
        for m in m_key_re.finditer(code_no_str):
            pos = m.start()
            lineno = _line_no(code_no_str, pos)
            if _in_spans(pos, loadconfig_body_spans) or _in_spans(pos, keyquery_body_spans):
                continue
            if _is_at_probe_class_member_scope(pos):
                line_text = lines_with_str[lineno - 1].strip()
                if re.fullmatch(
                    r"(?:(?:protected|private)\s+)?string\s+m_Key\s*(?:=\s*\"\"\s*)?;",
                    line_text,
                ):
                    total_m_key_decls += 1
                    continue
            violations.append(
                f"{rel}:{lineno}: m_Key fuera de su declaracion, LoadConfig() y KeyQuery()"
            )

        # Ningun Log() dentro de KeyQuery()
        for b_start, b_end in keyquery_body_spans:
            for lm in log_call_re.finditer(code_no_str, b_start, b_end):
                lineno = _line_no(code_no_str, lm.start())
                violations.append(f"{rel}:{lineno}: llamada a Log() dentro de KeyQuery()")

        # 5c: .key solo dentro de LoadConfig()
        for m in dot_key_re.finditer(code_no_str):
            total_dot_key += 1
            if not _in_spans(m.start(), loadconfig_body_spans):
                lineno = _line_no(code_no_str, m.start())
                violations.append(f"{rel}:{lineno}: acceso .key fuera de LoadConfig()")

        # 5d: dentro de LoadConfig(), cada llamada a Log( lleva solo un literal de texto
        for b_start, b_end in loadconfig_body_spans:
            for lm in log_call_re.finditer(code_no_str, b_start, b_end):
                open_p = lm.end() - 1
                close_p = _find_matching_paren(code_no_str, open_p)
                lineno = _line_no(code_no_str, lm.start())
                if close_p == -1 or close_p > b_end:
                    violations.append(f"{rel}:{lineno}: llamada a Log( sin cierre en LoadConfig()")
                    continue
                arg_str = code_with_str[open_p + 1 : close_p].strip()
                if not string_literal_re.fullmatch(arg_str):
                    violations.append(
                        f"{rel}:{lineno}: Log() en LoadConfig() debe llevar solo un literal de texto, recibido: {arg_str!r}"
                    )

        # 5e: cada llamada a KeyQuery(), fuera de su definicion, esta en una linea con .GET( o .POST( y sin Log(
        for m in key_query_re.finditer(code_no_str):
            if _in_spans(m.start(), keyquery_header_spans):
                continue
            total_keyquery_calls += 1
            lineno = _line_no(code_no_str, m.start())
            line_no_s = lines_no_str[lineno - 1]
            if not get_or_post_re.search(line_no_s):
                violations.append(
                    f"{rel}:{lineno}: llamada a KeyQuery() en una linea sin .GET( ni .POST("
                )
            if log_call_re.search(line_no_s):
                violations.append(
                    f"{rel}:{lineno}: llamada a KeyQuery() en la misma linea que Log("
                )

        # 5f: la variable de error de LoadFile solo aparece en su declaracion y en la linea de LoadFile
        for lf in loadfile_re.finditer(code_no_str):
            total_loadfile_calls += 1
            open_p = lf.end() - 1
            close_p = _find_matching_paren(code_no_str, open_p)
            lf_lineno = _line_no(code_no_str, lf.start())
            if close_p == -1:
                violations.append(f"{rel}:{lf_lineno}: LoadFile( sin parentesis de cierre")
                continue
            args_raw = code_no_str[open_p + 1 : close_p]
            parts = [p.strip() for p in args_raw.split(",")]
            if len(parts) != 3 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parts[2]):
                violations.append(
                    f"{rel}:{lf_lineno}: LoadFile debe tener un identificador como 3er argumento (err), recibido {args_raw!r}"
                )
                continue
            err_var = parts[2]
            err_re = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(err_var)}(?![A-Za-z0-9_])")
            decl_count = 0
            lf_count = 0
            for occ in err_re.finditer(code_no_str):
                occ_line = _line_no(code_no_str, occ.start())
                if occ_line == lf_lineno and open_p < occ.start() < close_p:
                    lf_count += 1
                    if log_call_re.search(lines_no_str[occ_line - 1]):
                        violations.append(
                            f"{rel}:{occ_line}: la linea de LoadFile contiene Log()"
                        )
                    continue
                decl_line = lines_with_str[occ_line - 1].strip()
                if re.fullmatch(
                    rf"string\s+{re.escape(err_var)}\s*(?:=\s*\"\"\s*)?;", decl_line
                ):
                    decl_count += 1
                    continue
                violations.append(
                    f"{rel}:{occ_line}: la variable de error {err_var!r} de LoadFile aparece fuera de su declaracion y de LoadFile"
                )
            if decl_count != 1 or lf_count != 1:
                violations.append(
                    f"{rel}:{lf_lineno}: la variable de error {err_var!r} debe tener 1 declaracion y 1 uso en LoadFile (decl={decl_count}, loadfile={lf_count})"
                )

    if total_log_defs != 1:
        violations.append(f"Se esperaba exactamente 1 definicion de Log(), encontradas {total_log_defs}")
    if total_loadconfig_defs != 1:
        violations.append(
            f"Se esperaba exactamente 1 definicion de LoadConfig(), encontradas {total_loadconfig_defs}"
        )
    if total_keyquery_defs != 1:
        violations.append(
            f"Se esperaba exactamente 1 definicion de KeyQuery(), encontradas {total_keyquery_defs}"
        )
    if total_m_key_decls != 1:
        violations.append(
            f"Se esperaba exactamente 1 declaracion de m_Key, encontradas {total_m_key_decls}"
        )
    if total_dot_key < 1:
        violations.append("No se encontro acceso .key dentro de LoadConfig()")
    if total_keyquery_calls < 1:
        violations.append("No se encontraron llamadas a KeyQuery()")
    if total_loadfile_calls != 1:
        violations.append(
            f"Se esperaba exactamente 1 llamada a LoadFile(), encontradas {total_loadfile_calls}"
        )

    return violations


def check_6_hello_body(probe_dir):
    """§6.2(6): HelloBody() contiene, en orden, \"proto\":\"qa0\", \"peer\":\" , \"inst\":\" , \"build\":\" y \"probe_ver\":\"dsbx-qa0\"."""
    violations = []
    hello_bodies = []
    for rel, path in _iter_c_files(probe_dir):
        text = path.read_text(encoding="utf-8", errors="replace")
        code_with_str = _strip_comments(text, blank_strings=False)
        code_no_str = _strip_comments(text, blank_strings=True)
        for d in _find_methods_in_c(code_no_str, "HelloBody"):
            b_start, b_end = d["body_span"]
            hello_bodies.append((rel, code_with_str[b_start:b_end]))

    if len(hello_bodies) != 1:
        return [f"Se esperaba exactamente 1 definicion de HelloBody(), encontradas {len(hello_bodies)}"]

    rel, body = hello_bodies[0]
    last_idx = -1
    for token in HELLO_BODY_TOKENS:
        idx = body.find(token, last_idx + 1 if last_idx >= 0 else 0)
        if idx == -1:
            if token in body:
                violations.append(
                    f"{rel}:HelloBody(): el fragmento {token} no aparece en el orden exigido"
                )
            else:
                violations.append(
                    f"{rel}:HelloBody(): falta el fragmento {token}"
                )
        else:
            last_idx = idx

    return violations


def check_7_required_pieces(probe_dir):
    """§6.2(7): Literales de dup, #ifdef DIAG_DEVELOPER con diag/retail, DSBX_QA_RPC_CAM >= 1000000, Send(...) y Event_OnRPC Insert/Remove."""
    violations = []
    c_files = _iter_c_files(probe_dir)
    if not c_files:
        return ["No se encontraron ficheros .c en la sonda"]

    combined_with_str = []
    combined_no_str = []
    for _, path in c_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        combined_with_str.append(_strip_comments(text, blank_strings=False))
        combined_no_str.append(_strip_comments(text, blank_strings=True))

    all_with_str = "\n".join(combined_with_str)
    all_no_str = "\n".join(combined_no_str)

    # 7a: literales de la conversion de dup
    for lit in DUP_CONVERSION_LITERALS:
        if lit not in all_with_str:
            violations.append(f"Falta el literal de conversion de dup: {lit}")

    # 7b: #ifdef DIAG_DEVELOPER con "diag" y "retail"
    ifdef_re = re.compile(
        r"#\s*ifdef\s+DIAG_DEVELOPER\b(.*?)#\s*else\b(.*?)#\s*endif\b",
        re.DOTALL,
    )
    ifdef_matches = list(ifdef_re.finditer(all_with_str))
    if not ifdef_matches:
        violations.append('Falta bloque #ifdef DIAG_DEVELOPER ... #else ... #endif')
    else:
        ok_diag_retail = any(
            '"diag"' in m.group(1) and '"retail"' in m.group(2)
            for m in ifdef_matches
        )
        if not ok_diag_retail:
            violations.append(
                'El bloque #ifdef DIAG_DEVELOPER debe contener "diag" en la rama #ifdef y "retail" en la rama #else'
            )

    # 7c: DSBX_QA_RPC_CAM definida una vez y con valor >= 1_000_000
    rpc_def_re = re.compile(
        r"\b(?:(?:static|const)\s+)*int\s+DSBX_QA_RPC_CAM\s*=\s*([+-]?\d+)\s*;"
    )
    rpc_defs = list(rpc_def_re.finditer(all_no_str))
    rpc_assigns = list(
        re.finditer(r"(?<![A-Za-z0-9_])DSBX_QA_RPC_CAM\s*=(?!=)", all_no_str)
    )
    if len(rpc_defs) != 1 or len(rpc_assigns) != 1:
        violations.append(
            f"DSBX_QA_RPC_CAM debe definirse exactamente una vez (defs={len(rpc_defs)}, asignaciones={len(rpc_assigns)})"
        )
    else:
        val = int(rpc_defs[0].group(1))
        if val < 1_000_000:
            violations.append(
                f"DSBX_QA_RPC_CAM debe tener un valor >= 1000000, tiene {val}"
            )

    # 7d: Send(null, DSBX_QA_RPC_CAM, true, null)
    send_re = re.compile(
        r"(?<![A-Za-z0-9_])Send\s*\(\s*null\s*,\s*DSBX_QA_RPC_CAM\s*,\s*true\s*,\s*null\s*\)"
    )
    if not send_re.search(all_no_str):
        violations.append("Falta la llamada Send(null, DSBX_QA_RPC_CAM, true, null)")

    # 7e: Event_OnRPC.Insert( y Event_OnRPC.Remove(, una vez cada uno
    insert_count = len(re.findall(r"\bEvent_OnRPC\s*\.\s*Insert\s*\(", all_no_str))
    remove_count = len(re.findall(r"\bEvent_OnRPC\s*\.\s*Remove\s*\(", all_no_str))
    if insert_count != 1:
        violations.append(
            f"Event_OnRPC.Insert( debe aparecer exactamente 1 vez, aparece {insert_count}"
        )
    if remove_count != 1:
        violations.append(
            f"Event_OnRPC.Remove( debe aparecer exactamente 1 vez, aparece {remove_count}"
        )

    return violations


def check_8_encoding_and_eol(probe_dir):
    """§6.2(8): Todos los ficheros de la sonda estan en UTF-8 sin BOM y solo con LF."""
    probe_dir = Path(probe_dir)
    files = sorted(p for p in probe_dir.rglob("*") if p.is_file())
    if not files:
        return ["No hay ficheros en la carpeta de la sonda"]

    violations = []
    for path in files:
        rel = path.relative_to(probe_dir).as_posix()
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            violations.append(f"{rel}: contiene BOM")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            violations.append(f"{rel}: no es UTF-8 valido ({exc})")
        if b"\r\n" in raw:
            violations.append(f"{rel}: contiene finales de linea CRLF")
        elif b"\r" in raw:
            violations.append(f"{rel}: contiene CR suelto")

    return violations


ALL_CHECKS = (
    check_1_mod_files,
    check_2_json_classes,
    check_3_write_ctors,
    check_4_forbidden_tokens,
    check_5_key_containment,
    check_6_hello_body,
    check_7_required_pieces,
    check_8_encoding_and_eol,
)


def run_all_checks(probe_dir):
    violations = []
    for fn in ALL_CHECKS:
        violations.extend(fn(probe_dir))
    return violations


# ---------------------------------------------------------------------------
# Fixture sintetica minima positiva (§6.2 «Fixtures»)
# ---------------------------------------------------------------------------

SYNTHETIC_CONFIG_CPP = """\
class CfgPatches
{
    class DayZSandbox_QA
    {
        units[] = {};
        weapons[] = {};
        requiredVersion = 0.1;
        requiredAddons[] = {"DZ_Data"};
    };
};

class CfgMods
{
    class DayZSandbox_QA
    {
        dir = "DayZSandbox_QA";
        name = "DayZSandbox_QA";
        type = "mod";
        dependencies[] = {"Mission"};
        class defs
        {
            class missionScriptModule
            {
                value = "";
                files[] = {"DayZSandbox_QA/scripts/5_Mission"};
            };
        };
    };
};
"""

SYNTHETIC_MESSAGES_C = """\
class DSBX_QA_Config
{
    string url;
    string key;
    int retry_ms;
}

class DSBX_QA_HelloResp
{
    int lease_ms;
}

class DSBX_QA_PollResp
{
    float now_ms;
    ref array<ref DSBX_QA_Op> ops;
}

class DSBX_QA_Op
{
    string op_id;
    string verb;
    string inst;
    float issued_ms;
    int ttl_ms;
    ref DSBX_QA_Args args;
}

class DSBX_QA_Args
{
    float x;
    float z;
    float fog;
    ref array<float> pos;
    ref array<float> ypr;
    int count;
    int interval_ms;
    int seq0;
    string client_inst;
}

class DSBX_QA_RpcEntry
{
    int seq;
    float recv_ms;
    float lease_age_ms;
    string decision;
}

class DSBX_QA_Read
{
    ref array<string> has;
    int frame;
    float tick_s;
    float y;
    float fog;
    ref array<float> pos;
    ref array<float> ypr;
    ref array<ref DSBX_QA_RpcEntry> rpc_log;

    void DSBX_QA_Read()
    {
        has = new array<string>();
        pos = new array<float>();
        pos.Insert(0.0);
        pos.Insert(0.0);
        pos.Insert(0.0);
        ypr = new array<float>();
        ypr.Insert(0.0);
        ypr.Insert(0.0);
        ypr.Insert(0.0);
        rpc_log = new array<ref DSBX_QA_RpcEntry>();
    }
}

class DSBX_QA_Result
{
    string op_id;
    string status;
    string reason;
    int dup;
    float recv_ms;
    float done_ms;
    int frame_recv;
    int frame_done;
    ref DSBX_QA_Read read;

    void DSBX_QA_Result()
    {
        read = new DSBX_QA_Read();
    }
}
"""

SYNTHETIC_PROBE_C = """\
static const int DSBX_QA_RPC_CAM = 26102701;

class DSBX_QA_Callback : RestCallback
{
    DSBX_QA_Probe m_Probe;
}

class DSBX_QA_Probe : Managed
{
    string m_Role;
    string m_Inst;
    string m_Build;
    string m_Url;
    string m_Key;
    int m_RetryMs;
    int m_Frame;
    RestContext m_Ctx;

    void DSBX_QA_Probe(string role)
    {
        m_Role = role;
#ifdef DIAG_DEVELOPER
        m_Build = "diag";
#else
        m_Build = "retail";
#endif
        if (m_Role == "client")
        {
            DayZGame.Event_OnRPC.Insert(this.OnRpc);
        }
    }

    void ~DSBX_QA_Probe()
    {
        Shutdown();
    }

    void Shutdown()
    {
        if (m_Role == "client")
        {
            DayZGame.Event_OnRPC.Remove(this.OnRpc);
        }
    }

    void Log(string msg)
    {
        Print("[DSBX_QA] " + msg);
    }

    bool LoadConfig()
    {
        DSBX_QA_Config cfg;
        string err;
        if (!JsonFileLoader<DSBX_QA_Config>.LoadFile("$profile:dsbx_qa.json", cfg, err))
        {
            Log("config unreadable");
            return false;
        }
        if (cfg.key == "" || cfg.url.IndexOf("http://127.0.0.1:") != 0)
        {
            Log("config invalid");
            return false;
        }
        m_Url = cfg.url;
        m_Key = cfg.key;
        m_RetryMs = cfg.retry_ms;
        Log("config usable");
        return true;
    }

    string KeyQuery()
    {
        return "key=" + m_Key;
    }

    string HelloBody()
    {
        return "{\\"proto\\":\\"qa0\\",\\"peer\\":\\"" + m_Role + "\\",\\"inst\\":\\"" + m_Inst + "\\",\\"build\\":\\"" + m_Build + "\\",\\"probe_ver\\":\\"dsbx-qa0\\"}";
    }

    void SendHello(DSBX_QA_Callback cb)
    {
        m_Ctx.POST("hello?" + KeyQuery(), HelloBody(), cb);
    }

    void SendPoll(DSBX_QA_Callback cb, float tick_s)
    {
        m_Ctx.GET("poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame.ToString() + "&tick_s=" + tick_s.ToString(), cb);
    }

    bool SendResult(DSBX_QA_Result result, DSBX_QA_Callback cb)
    {
        JsonSerializer js = new JsonSerializer();
        string body;
        js.WriteToString(result, false, body);
        int c0 = body.Replace("\\"dup\\":0", "\\"dup\\":false");
        int c1 = body.Replace("\\"dup\\":1", "\\"dup\\":true");
        if (c0 + c1 != 1)
        {
            return false;
        }
        m_Ctx.POST("result?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst, body, cb);
        return true;
    }

    void SendCamRpc(int seq, string target_inst, array<float> pos, array<float> ypr)
    {
        ScriptRPC rpc = new ScriptRPC();
        rpc.Write(seq);
        rpc.Write(target_inst);
        rpc.Write(pos);
        rpc.Write(ypr);
        rpc.Send(null, DSBX_QA_RPC_CAM, true, null);
    }

    void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
    {
        if (rpc_type != DSBX_QA_RPC_CAM)
        {
            return;
        }
    }
}
"""

SYNTHETIC_MISSION_C = """\
modded class MissionServer
{
    ref DSBX_QA_Probe m_DsbxQaProbe;

    override void OnMissionStart()
    {
        super.OnMissionStart();
        m_DsbxQaProbe = new DSBX_QA_Probe("server");
    }
}

modded class MissionGameplay
{
    ref DSBX_QA_Probe m_DsbxQaProbe;

    override void OnMissionStart()
    {
        super.OnMissionStart();
        m_DsbxQaProbe = new DSBX_QA_Probe("client");
    }
}
"""


def make_synthetic_files():
    return {
        "$PBOPREFIX$": b"DayZSandbox_QA\n",
        "include.lst": b"*.c\n",
        "config.cpp": SYNTHETIC_CONFIG_CPP.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Messages.c": SYNTHETIC_MESSAGES_C.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Probe.c": SYNTHETIC_PROBE_C.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Mission.c": SYNTHETIC_MISSION_C.encode("utf-8"),
    }


def write_probe_tree(root, files_map):
    root = Path(root)
    for rel, raw in files_map.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
    return root


class ProbeStaticTests(unittest.TestCase):
    def _assert_mutation_caught_by(self, mutate_fn, expected_check_fn):
        with tempfile.TemporaryDirectory() as tmp:
            files = make_synthetic_files()
            mutate_fn(files)
            write_probe_tree(tmp, files)
            violations = expected_check_fn(tmp)
            self.assertTrue(
                len(violations) >= 1,
                f"{expected_check_fn.__name__} debio detectar al menos 1 violacion y devolvio {violations!r}",
            )
            for other_fn in ALL_CHECKS:
                if other_fn is expected_check_fn:
                    continue
                self.assertEqual(
                    other_fn(tmp),
                    [],
                    f"{other_fn.__name__} debio seguir en [] sobre la mutacion de {expected_check_fn.__name__}",
                )

    def test_synthetic_positive_fixture_zero_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_probe_tree(tmp, make_synthetic_files())
            for check_fn in ALL_CHECKS:
                self.assertEqual(
                    check_fn(tmp),
                    [],
                    f"La sonda sintetica positiva dio violaciones en {check_fn.__name__}",
                )
            self.assertEqual(run_all_checks(tmp), [])

    def test_neg_check1_mod_files(self):
        # 1a: $PBOPREFIX$ incorrecto
        def mut_prefix(files):
            files["$PBOPREFIX$"] = b"WrongPrefix\n"

        self._assert_mutation_caught_by(mut_prefix, check_1_mod_files)

        # 1b: include.lst incorrecto
        def mut_include(files):
            files["include.lst"] = b"*.cpp\n"

        self._assert_mutation_caught_by(mut_include, check_1_mod_files)

        # 1c: config.cpp con modulo extra worldScriptModule
        def mut_config(files):
            files["config.cpp"] = files["config.cpp"].replace(
                b'files[] = {"DayZSandbox_QA/scripts/5_Mission"};',
                b'files[] = {"DayZSandbox_QA/scripts/4_World"};',
            )

        self._assert_mutation_caught_by(mut_config, check_1_mod_files)

    def test_neg_check2_renamed_json_field(self):
        # Mutacion obligatoria 1 de §6.2: un campo JSON renombrado
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"int lease_ms;", b"int lease_duration_ms;")

        self._assert_mutation_caught_by(mut, check_2_json_classes)

    def test_neg_check2_extra_member(self):
        # Mutacion obligatoria 2 de §6.2: un miembro de mas
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"int lease_ms;", b"int lease_ms;\n    int extra_field;")

        self._assert_mutation_caught_by(mut, check_2_json_classes)

    def test_neg_check3_uncreated_ref_in_ctor(self):
        # Mutacion obligatoria 3 de §6.2: un ref sin crear en el constructor
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"        rpc_log = new array<ref DSBX_QA_RpcEntry>();\n", b"")

        self._assert_mutation_caught_by(mut, check_3_write_ctors)

    def test_neg_check4_enable_debug_added(self):
        # Mutacion obligatoria 4 de §6.2: EnableDebug(true) anadido
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n        m_Ctx.EnableDebug(true);\n",
            )

        self._assert_mutation_caught_by(mut, check_4_forbidden_tokens)

    def test_neg_check5_print_outside_log(self):
        # Mutacion obligatoria 5 de §6.2: un Print("x") fuera de Log()
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b'    void SendHello(DSBX_QA_Callback cb)\n    {\n        Print("x");\n',
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_log_m_key_outside_allowed(self):
        # Mutacion obligatoria 6 de §6.2: Log(m_Key) fuera de LoadConfig() y de KeyQuery()
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n        Log(m_Key);\n",
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_key_query_without_get_or_post(self):
        # Mutacion obligatoria 7 de §6.2: string r = "poll?" + KeyQuery(); en una linea sin GET ni POST
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b'    void SendHello(DSBX_QA_Callback cb)\n    {\n        string r = "poll?" + KeyQuery();\n',
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_log_err_inside_load_config(self):
        # Mutacion obligatoria 8 de §6.2: Log(err) dentro de LoadConfig(), con la variable de error de LoadFile
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'            Log("config unreadable");',
                b"            Log(err);",
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_dot_key_outside_load_config(self):
        # Cobertura adicional de §6.2(5): acceso .key fuera de LoadConfig()
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n        DSBX_QA_Config c;\n        string k = c.key;\n",
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check6_misspelled_proto_in_hello_body(self):
        # Mutacion obligatoria 9 de §6.2: proto mal escrito en HelloBody()
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'{\\"proto\\":\\"qa0\\"',
                b'{\\"prto\\":\\"qa0\\"',
            )

        self._assert_mutation_caught_by(mut, check_6_hello_body)

    def test_neg_check6_wrong_order_in_hello_body(self):
        # Cobertura adicional de §6.2(6): campos desordenados en HelloBody()
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'{\\"proto\\":\\"qa0\\",\\"peer\\":\\"" + m_Role',
                b'{\\"peer\\":\\"" + m_Role + "\\",\\"proto\\":\\"qa0\\"',
            )

        self._assert_mutation_caught_by(mut, check_6_hello_body)

    def test_neg_check7_remove_deleted(self):
        # Mutacion obligatoria 10 de §6.2: el Remove quitado
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"            DayZGame.Event_OnRPC.Remove(this.OnRpc);\n",
                b"",
            )

        self._assert_mutation_caught_by(mut, check_7_required_pieces)

    def test_neg_check7_other_pieces(self):
        # Cobertura adicional de §6.2(7): dup, #ifdef DIAG_DEVELOPER, DSBX_QA_RPC_CAM < 1000000, Send(...)
        def mut_dup(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(b'\\"dup\\":false', b'\\"dup\\":0')

        self._assert_mutation_caught_by(mut_dup, check_7_required_pieces)

        def mut_ifdef(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(b"#ifdef DIAG_DEVELOPER", b"#ifdef OTHER_FLAG")

        self._assert_mutation_caught_by(mut_ifdef, check_7_required_pieces)

        def mut_rpc_val(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"DSBX_QA_RPC_CAM = 26102701;",
                b"DSBX_QA_RPC_CAM = 999999;",
            )

        self._assert_mutation_caught_by(mut_rpc_val, check_7_required_pieces)

        def mut_send(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"rpc.Send(null, DSBX_QA_RPC_CAM, true, null);",
                b"rpc.Send(null, DSBX_QA_RPC_CAM, false, null);",
            )

        self._assert_mutation_caught_by(mut_send, check_7_required_pieces)

    def test_neg_check8_utf8_bom(self):
        # Mutacion obligatoria 11 de §6.2: un BOM
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Mission.c"] = (
                b"\xef\xbb\xbf" + files["scripts/5_Mission/DSBX_QA_Mission.c"]
            )

        self._assert_mutation_caught_by(mut, check_8_encoding_and_eol)

    def test_neg_check8_crlf(self):
        # Mutacion obligatoria 12 de §6.2: un CRLF
        def mut(files):
            files["$PBOPREFIX$"] = b"DayZSandbox_QA\r\n"

        self._assert_mutation_caught_by(mut, check_8_encoding_and_eol)

    def test_real_probe_zero_violations(self):
        if not REAL_PROBE_DIR.is_dir():
            self.skipTest(f"Carpeta de la sonda real ausente: {REAL_PROBE_DIR}")
        for check_fn in ALL_CHECKS:
            self.assertEqual(
                check_fn(REAL_PROBE_DIR),
                [],
                f"La sonda real tiene violaciones en {check_fn.__name__}",
            )


if __name__ == "__main__":
    unittest.main()
