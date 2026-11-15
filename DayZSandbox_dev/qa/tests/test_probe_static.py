"""Prueba estatica del contrato comun F0.3-0 de la sonda QA en Enforce (brief F0.3-0 §6.1 y §14)."""

import ast
import re
import tempfile
import unittest
from pathlib import Path

QA_DIR = Path(__file__).resolve().parents[1]
REAL_PROBE_DIR = QA_DIR / "probe" / "DayZSandbox_QA"
WIRE_PY_PATH = QA_DIR / "wire.py"

EXTENSION_SPECS = (
    ("Persist", "DSBX_QA_X_Persist", "per_", 26102800, 26102809),
    ("Actor", "DSBX_QA_X_Actor", "act_", 26102810, 26102819),
    ("Cam", "DSBX_QA_X_Cam", "scam_", 26102820, 26102829),
    ("Cot", "DSBX_QA_X_Cot", "cot_", 26102830, 26102839),
    ("Env", "DSBX_QA_X_Env", "env_", 26102840, 26102849),
    ("Take", "DSBX_QA_X_Take", "take_", 26102850, 26102859),
    ("Perf", "DSBX_QA_X_Perf", "perf_", 26102860, 26102869),
    ("Map", "DSBX_QA_X_Map", "map_", 26102870, 26102879),
    ("Base", "DSBX_QA_X_Base", "qa_", 26102880, 26102889),
)

EXTENSION_BY_NAME = {name: (idx, cls_name, prefix, lo, hi) for idx, (name, cls_name, prefix, lo, hi) in enumerate(EXTENSION_SPECS)}
ALL_EXT_PREFIXES = tuple(spec[2] for spec in EXTENSION_SPECS)

CORE_5_MISSION_C_FILES = (
    "scripts/5_Mission/DSBX_QA_Stamp.c",
    "scripts/5_Mission/DSBX_QA_Messages.c",
    "scripts/5_Mission/DSBX_QA_Jobs.c",
    "scripts/5_Mission/DSBX_QA_Probe.c",
    "scripts/5_Mission/DSBX_QA_Mission.c",
)

EXT_5_MISSION_C_FILES = tuple(
    f"scripts/5_Mission/DSBX_QA_X_{name}.c" for name, _, _, _, _ in EXTENSION_SPECS
)

EXPECTED_C_FILES = (
    "scripts/4_World/DSBX_QA_W_Actor.c",
    *CORE_5_MISSION_C_FILES,
    *EXT_5_MISSION_C_FILES,
)

EXPECTED_REL_FILES = (
    "$PBOPREFIX$",
    "include.lst",
    "config.cpp",
    *EXPECTED_C_FILES,
)

PAYLOAD_9_MEMBERS = [
    ("ref array<string>", "sk"),
    ("ref array<string>", "sv"),
    ("ref array<string>", "nk"),
    ("ref array<float>", "nv"),
    ("ref array<string>", "ncol"),
    ("ref array<float>", "ncell"),
    ("ref array<string>", "scol"),
    ("ref array<string>", "scell"),
    ("int", "rows"),
]

EXPECTED_JSON_CLASSES = {
    "DSBX_QA_Config": [
        ("string", "url"),
        ("string", "key"),
        ("int", "retry_ms"),
        ("int", "callback_budget"),
    ],
    "DSBX_QA_HelloResp": [
        ("bool", "ok"),
        ("int", "lease_ms"),
    ],
    "DSBX_QA_AckResp": [
        ("bool", "ok"),
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
        *PAYLOAD_9_MEMBERS,
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
        *PAYLOAD_9_MEMBERS,
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
    ".Replace(",
)

HELLO_BODY_TOKENS = (
    r'\"proto\":\"qa0\"',
    r'\"peer\":\"',
    r'\"inst\":\"',
    r'\"build\":\"',
    r'\"probe_ver\":\"dsbx-qa1+',
    "DSBX_QA_STAMP",
)

DUP_CONVERSION_LITERALS = (
    r'\"dup\":0',
    r'\"dup\":1',
    r'\"dup\":false',
    r'\"dup\":true',
)

EXT_REQUIRED_METHODS = (
    "Init",
    "Handles",
    "OnStartOp",
    "OnTick",
    "OnJobEnd",
    "OnRpc",
    "OnShutdown",
)

JOBMGR_REQUIRED_METHODS = (
    "StartJob",
    "AppendRow",
    "GetState",
    "EndJob",
)

ORDERED_LOG_MEMBERS = (
    "m_CacheOrder",
    "m_RpcLog",
    "m_PingLog",
    "m_EmitLog",
)

ALLOWED_CFG_FIELDS = {"url", "retry_ms", "callback_budget", "key"}


def _read_python_wire_cap(wire_py_path=None):
    path = Path(wire_py_path) if wire_py_path is not None else WIRE_PY_PATH
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\s*WIRE_CAP\s*(?::\s*int\s*)?=\s*([+-]?\d+)\b", text, re.MULTILINE)
    if not m:
        return None
    return int(m.group(1))


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


def _extract_c_string_literals(code_with_strings):
    """Devuelve lista de (start_offset, unescaped_value) para cada literal C de cadena."""
    literals = []
    n = len(code_with_strings)
    i = 0
    while i < n:
        if code_with_strings[i] == '"':
            start = i
            i += 1
            chars = []
            while i < n:
                ch = code_with_strings[i]
                if ch == "\\" and i + 1 < n:
                    chars.append(code_with_strings[i + 1])
                    i += 2
                elif ch == '"':
                    i += 1
                    break
                else:
                    chars.append(ch)
                    i += 1
            literals.append((start, "".join(chars)))
        else:
            i += 1
    return literals


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


def _split_top_level_spans(code_no_strings, start_idx, end_idx, sep=","):
    """Parte el rango [start_idx, end_idx) por sep en profundidad 0 de (), [] y {}."""
    if not code_no_strings[start_idx:end_idx].strip():
        return []
    spans = []
    cur_start = start_idx
    depth = 0
    for idx in range(start_idx, end_idx):
        ch = code_no_strings[idx]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth > 0:
                depth -= 1
        elif ch == sep and depth == 0:
            spans.append((cur_start, idx))
            cur_start = idx + 1
    spans.append((cur_start, end_idx))
    return spans


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
        r"\b(?:(?:protected|private|override|static)\s+)*(?:void|bool|string|int|float)\s+(~?[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{",
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


def _strip_directive_lines(code):
    """Sustituye por espacios las lineas de preprocesador (#...) conservando longitud y saltos de linea."""
    out = list(code)
    pos = 0
    n = len(code)
    while pos < n:
        end = code.find("\n", pos)
        if end == -1:
            end = n
        if code[pos:end].lstrip().startswith("#"):
            for k in range(pos, end):
                out[k] = " "
        pos = end + 1
    return "".join(out)


_METHOD_DEF_RE = re.compile(
    r"(?<![.\w])(?:(?:protected|private|override|static)\s+)*"
    r"(?:ref\s+)?(?:void|bool|string|int|float|[A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^;{}]*>)?\s+"
    r"(~?[A-Za-z_][A-Za-z0-9_]*)\s*\(([^;{}()]*)\)\s*\{"
)

_TYPE_MODIFIER_RE = re.compile(r"^(?:(?:ref|out|autoptr|notnull|const|private|protected|static)\s+)+")

_LOCAL_DECL_RE = re.compile(
    r"(?<![.\w])((?:ref\s+)?[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^;{}()]*>)?)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*(?==|;)"
)

_MEMBER_DECL_RE = re.compile(
    r"(?<![.\w])((?:ref\s+)?[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^;{}()]*>)?)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*;"
)


def _decl_type(raw_type):
    norm = re.sub(r"\s+", " ", raw_type.strip())
    return _TYPE_MODIFIER_RE.sub("", norm).strip()


def _is_restcontext_type(raw_type):
    return _decl_type(raw_type) == "RestContext"


def _find_methods_with_bodies(code_no_strings, start=0, end=None):
    """Devuelve (name, params, header_span, body_span, full_span) de cada metodo con cuerpo en [start, end)."""
    if end is None:
        end = len(code_no_strings)
    results = []
    pos = start
    while pos < end:
        m = _METHOD_DEF_RE.search(code_no_strings, pos, end)
        if not m:
            break
        open_brace = m.end() - 1
        close_brace = _find_matching_brace(code_no_strings, open_brace)
        if close_brace == -1 or close_brace > end:
            break
        results.append(
            {
                "name": m.group(1),
                "params": m.group(2),
                "header_span": (m.start(), open_brace),
                "body_span": (open_brace + 1, close_brace),
                "full_span": (m.start(), close_brace + 1),
            }
        )
        pos = close_brace + 1
    return results


def _parse_param_decls(params_text):
    decls = {}
    for s, e in _split_top_level_spans(params_text, 0, len(params_text), sep=","):
        part = params_text[s:e].strip()
        if not part:
            continue
        part = part.split("=", 1)[0].strip()
        m = re.match(r"^(.+?)\s+([A-Za-z_][A-Za-z0-9_]*)$", part)
        if m:
            decls[m.group(2)] = m.group(1)
    return decls


def _collect_member_decls(code_no_strings, class_body_start, class_body_end):
    methods = _find_methods_with_bodies(code_no_strings, class_body_start, class_body_end)
    masked = list(code_no_strings[class_body_start:class_body_end])
    for meth in methods:
        s = max(0, meth["full_span"][0] - class_body_start)
        e = min(len(masked), meth["full_span"][1] - class_body_start)
        for k in range(s, e):
            if masked[k] != "\n":
                masked[k] = " "
    decls = {}
    for m in _MEMBER_DECL_RE.finditer("".join(masked)):
        decls[m.group(2)] = m.group(1)
    return decls


def _receiver_is_restcontext(code_no_strings, call_offset, recv_id):
    """Comprueba que recv_id esta declarado RestContext en el ambito efectivo de la llamada."""
    class_span = None
    for cname, _hdr, bs, be in _extract_named_blocks(code_no_strings, "class"):
        if bs <= call_offset <= be:
            class_span = (cname, bs, be)
            break
    if class_span is None:
        return False, "no se pudo determinar la clase que contiene la llamada"
    cname, bs, be = class_span

    method = None
    for meth in _find_methods_with_bodies(code_no_strings, bs, be):
        if meth["body_span"][0] <= call_offset <= meth["body_span"][1]:
            method = meth
            break

    if method is not None:
        param_type = _parse_param_decls(method["params"]).get(recv_id)
        if param_type is not None:
            if _is_restcontext_type(param_type):
                return True, None
            return False, (
                f"en {cname}::{method['name']} el parametro {recv_id!r} es de tipo "
                f"{_decl_type(param_type)!r}, no RestContext"
            )
        body_start, body_end = method["body_span"]
        local_type = None
        for m in _LOCAL_DECL_RE.finditer(code_no_strings, body_start, body_end):
            if m.start() >= call_offset:
                break
            if m.group(2) == recv_id:
                local_type = m.group(1)
        if local_type is not None:
            if _is_restcontext_type(local_type):
                return True, None
            return False, (
                f"en {cname}::{method['name']} la local {recv_id!r} es de tipo "
                f"{_decl_type(local_type)!r}, no RestContext"
            )

    member_type = _collect_member_decls(code_no_strings, bs, be).get(recv_id)
    if member_type is None:
        return False, f"{recv_id!r} no esta declarado en la clase {cname}"
    if _is_restcontext_type(member_type):
        return True, None
    return False, (
        f"en {cname}, el miembro {recv_id!r} es de tipo {_decl_type(member_type)!r}, no RestContext"
    )


def _line_no(text, offset):
    return text.count("\n", 0, offset) + 1


def _classify_extension_c_file(rel_posix):
    """Si rel_posix es un fichero de extension 5_Mission/DSBX_QA_X_<Name>[_<algo>].c, devuelve <Name>, si no None."""
    m = re.fullmatch(
        r"scripts/5_Mission/DSBX_QA_X_(Persist|Actor|Cam|Cot|Env|Take|Perf|Map|Base)(?:_([A-Za-z0-9_]+))?\.c",
        rel_posix,
    )
    if not m:
        return None
    return m.group(1)


def _is_allowed_c_file(rel_posix):
    if rel_posix in EXPECTED_C_FILES:
        return True
    if _classify_extension_c_file(rel_posix) is not None:
        return True
    if re.fullmatch(r"scripts/4_World/DSBX_QA_W_Actor_[A-Za-z0-9_]+\.c", rel_posix):
        return True
    return False


# ---------------------------------------------------------------------------
# Las comprobaciones del contrato estatico (§6.1 y §14)
# ---------------------------------------------------------------------------


def check_1_mod_files(probe_dir):
    """§6.1(1): Ficheros de la sonda, sello DSBX_QA_Stamp.c y config.cpp con 4_World y 5_Mission."""
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
                    (
                        'dependencies[] = {"World", "Mission"}',
                        r'\bdependencies\s*\[\s*\]\s*=\s*\{\s*"World"\s*,\s*"Mission"\s*\}\s*;',
                    ),
                ):
                    if not re.search(pat, mod_body, re.DOTALL):
                        violations.append(f"config.cpp: CfgMods::DayZSandbox_QA sin {desc}")

                if re.search(r"\binputs\s*=", mod_no_str):
                    if not re.search(r'\binputs\s*=\s*"DayZSandbox_QA/inputs\.xml"\s*;', mod_body):
                        violations.append(
                            'config.cpp: inputs en CfgMods::DayZSandbox_QA debe ser exactamente "DayZSandbox_QA/inputs.xml"'
                        )
                    elif not (probe_dir / "inputs.xml").is_file():
                        violations.append("config.cpp declara inputs pero falta inputs.xml en la sonda")
                elif (probe_dir / "inputs.xml").is_file():
                    violations.append(
                        'inputs.xml presente sin inputs = "DayZSandbox_QA/inputs.xml"; en CfgMods::DayZSandbox_QA'
                    )

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
                    expected_modules = {"worldScriptModule", "missionScriptModule"}
                    if set(modules.keys()) != expected_modules:
                        violations.append(
                            f"config.cpp: defs debe tener exactamente {sorted(expected_modules)}, tiene {sorted(modules.keys())}"
                        )
                    for mod_name, expected_path in (
                        ("worldScriptModule", "DayZSandbox_QA/scripts/4_World"),
                        ("missionScriptModule", "DayZSandbox_QA/scripts/5_Mission"),
                    ):
                        if mod_name in modules:
                            mbs, mbe = modules[mod_name]
                            m_body = defs_clean[mbs:mbe]
                            if not re.search(r'\bvalue\s*=\s*""\s*;', m_body, re.DOTALL):
                                violations.append(f'config.cpp: {mod_name} sin value = ""')
                            if not re.search(
                                rf'\bfiles\s*\[\s*\]\s*=\s*\{{\s*"{re.escape(expected_path)}"\s*\}}\s*;',
                                m_body,
                                re.DOTALL,
                            ):
                                violations.append(
                                    f'config.cpp: {mod_name} sin files[] = {{"{expected_path}"}}'
                                )

    for rel in EXPECTED_C_FILES:
        if not (probe_dir / rel).is_file():
            violations.append(f"{rel}: fichero ausente")

    all_c = sorted(p.relative_to(probe_dir).as_posix() for p in probe_dir.rglob("*.c"))
    for rel in all_c:
        if not _is_allowed_c_file(rel):
            violations.append(f"{rel}: fichero .c no autorizado por §6.1(1)")

    stamp_path = probe_dir / "scripts/5_Mission/DSBX_QA_Stamp.c"
    if stamp_path.is_file():
        stamp_clean = _strip_comments(
            stamp_path.read_text(encoding="utf-8", errors="replace"),
            blank_strings=False,
        ).strip()
        if not re.fullmatch(
            r'(?:static\s+)?const\s+string\s+DSBX_QA_STAMP\s*=\s*"(?:unstamped|[0-9a-f]{16})"\s*;',
            stamp_clean,
        ):
            violations.append(
                'scripts/5_Mission/DSBX_QA_Stamp.c: debe declarar exactamente const string DSBX_QA_STAMP = "unstamped"; (o 16 hex en minúsculas)'
            )

    return violations


def check_2_json_classes(probe_dir):
    """§6.1(2) + §14 (F02-H4, F02-H5): DSBX_QA_Messages.c tiene exactamente las 9 clases JSON con sus miembros exactos."""
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
    """§6.1(3): En las clases que se escriben, el constructor crea cada miembro ref (incluidos los 8 nuevos de DSBX_QA_Read)."""
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
    """§6.1(4): Ningun .c contiene GET_now, POST_now, FILE_now, .FILE(, .reset(, EnableDebug, DebugList, JsonLoadFile, GetCurrentCamera ni .Replace(."""
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
        (".Replace(", re.compile(r"\.\s*Replace\s*\(")),
    ]
    for rel, path in _iter_c_files(probe_dir):
        text = path.read_text(encoding="utf-8", errors="replace")
        clean = _strip_comments(text, blank_strings=False)
        for label, pat in patterns:
            for m in pat.finditer(clean):
                lineno = _line_no(clean, m.start())
                violations.append(f"{rel}:{lineno}: contiene API prohibida {label!r}")
    return violations


def _find_http_get_post_calls(code_no_str):
    """Localiza llamadas <receptor>.GET(...) y <receptor>.POST(...) y devuelve sus spans de argumentos."""
    calls = []
    pat = re.compile(
        r"(?:[A-Za-z_][A-Za-z0-9_]*(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*)*)\s*\.\s*(GET|POST)\s*\("
    )
    pos = 0
    while pos < len(code_no_str):
        m = pat.search(code_no_str, pos)
        if not m:
            break
        open_p = m.end() - 1
        close_p = _find_matching_paren(code_no_str, open_p)
        if close_p == -1:
            pos = m.end()
            continue
        arg_spans = _split_top_level_spans(code_no_str, open_p + 1, close_p, sep=",")
        calls.append(
            {
                "method": m.group(1),
                "call_span": (m.start(), close_p + 1),
                "paren_span": (open_p, close_p),
                "arg_spans": arg_spans,
            }
        )
        pos = m.end()
    return calls


def check_5_key_containment(probe_dir):
    """§6.1(5) + §14 F02-H6: Contencion de la clave y de DSBX_QA_Config por flujo de datos y analisis de argumentos de GET/POST."""
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
    key_query_re = re.compile(r"(?<![A-Za-z0-9_])KeyQuery(?![A-Za-z0-9_])")
    loadfile_re = re.compile(r"\bLoadFile\s*\(")
    cfg_type_re = re.compile(r"(?<![A-Za-z0-9_])DSBX_QA_Config(?![A-Za-z0-9_])")
    string_literal_re = re.compile(r'^"(?:\\.|[^"\\])*"$')

    total_log_defs = 0
    total_loadconfig_defs = 0
    total_keyquery_defs = 0
    total_m_key_decls = 0
    total_dot_key = 0
    total_keyquery_calls = 0
    total_loadfile_calls = 0

    # 5h (H7 de Sol r1, N3 de Sol r3): el flujo de la clave solo puede ir al RestContext nativo. El receptor de
    # cada .GET/.POST con KeyQuery() tiene que estar declarado RestContext en su ambito efectivo (parametro/local
    # del metodo o miembro de la clase que contiene la llamada), y la sonda no puede definir metodos propios
    # GET/POST (un envoltorio podria registrar la peticion con la clave). Las lineas de preprocesador se ignoran
    # al buscar la firma y la llave, conservando la numeracion de linea.
    http_method_def_re = re.compile(r"(?<![.\w])(GET|POST)\s*\([^;{}()]*\)\s*\{")

    for rel, path in c_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        code_with_str = _strip_comments(text, blank_strings=False)
        code_no_str = _strip_comments(text, blank_strings=True)
        code_no_directives = _strip_directive_lines(code_no_str)
        lines_no_str = code_no_str.splitlines()
        lines_with_str = code_with_str.splitlines()

        for hm in http_method_def_re.finditer(code_no_directives):
            violations.append(
                f"{rel}:{_line_no(code_no_str, hm.start())}: la sonda no puede definir un metodo propio {hm.group(1)}() "
                "(un envoltorio de RestContext podria registrar la peticion con la clave)"
            )

        log_defs = _find_methods_in_c(code_no_str, "Log")
        loadconfig_defs = _find_methods_in_c(code_no_str, "LoadConfig")
        keyquery_defs = _find_methods_in_c(code_no_str, "KeyQuery")

        total_log_defs += len(log_defs)
        total_loadconfig_defs += len(loadconfig_defs)
        total_keyquery_defs += len(keyquery_defs)

        class_blocks = _extract_named_blocks(code_no_str, "class")
        probe_class_spans = [
            (bs, be) for cname, _, bs, be in class_blocks if cname == "DSBX_QA_Probe"
        ]
        cfg_class_full_spans = [
            (hs, be + 1) for cname, hs, _, be in class_blocks if cname == "DSBX_QA_Config"
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

        # 5b (F02-H6): DSBX_QA_Config solo puede existir en su definicion de clase y como local dentro de LoadConfig()
        for m in cfg_type_re.finditer(code_no_str):
            pos = m.start()
            if _in_spans(pos, cfg_class_full_spans):
                continue
            if not _in_spans(pos, loadconfig_body_spans):
                lineno = _line_no(code_no_str, pos)
                violations.append(
                    f"{rel}:{lineno}: DSBX_QA_Config usado fuera de LoadConfig() (prohibido miembro o referencia externa)"
                )

        # 5c (F02-H6): m_Key solo en su declaracion, en LoadConfig() (solo asignacion desde cfg.key o comparacion con "") y en KeyQuery() (solo return "key=" + m_Key)
        for m in m_key_re.finditer(code_no_str):
            pos = m.start()
            lineno = _line_no(code_no_str, pos)
            if _in_spans(pos, loadconfig_body_spans):
                b_start, b_end = next(
                    (bs, be) for bs, be in loadconfig_body_spans if bs <= pos < be
                )
                before_str = code_with_str[b_start:pos]
                after_str = code_with_str[m.end() : b_end]
                allowed_assign = bool(
                    re.search(r"(?:^|[;{}])\s*(?:this\s*\.\s*)?$", before_str)
                    and re.match(r"^\s*=(?!=)\s*[A-Za-z_][A-Za-z0-9_]*\s*\.\s*key\s*;", after_str)
                )
                allowed_cmp = bool(
                    (
                        re.match(r'^\s*(?:==|!=)\s*""', after_str)
                        and not re.search(r"(?<![=!<>])=(?!=)\s*(?:this\s*\.\s*)?$", before_str)
                    )
                    or re.search(r'""\s*(?:==|!=)\s*(?:this\s*\.\s*)?$', before_str)
                )
                if not (allowed_assign or allowed_cmp):
                    violations.append(
                        f"{rel}:{lineno}: uso no permitido de m_Key en LoadConfig(): {lines_with_str[lineno - 1].strip()!r}"
                    )
                continue
            if _in_spans(pos, keyquery_body_spans):
                b_start, b_end = next(
                    (bs, be) for bs, be in keyquery_body_spans if bs <= pos < be
                )
                kq_body = code_with_str[b_start:b_end].strip()
                if not re.fullmatch(
                    r'return\s+"key="\s*\+\s*(?:this\s*\.\s*)?m_Key\s*;',
                    kq_body,
                ):
                    violations.append(
                        f"{rel}:{lineno}: en KeyQuery(), m_Key solo puede usarse en 'return \"key=\" + m_Key;': {kq_body!r}"
                    )
                continue
            if _is_at_probe_class_member_scope(pos):
                line_text = lines_with_str[lineno - 1].strip()
                if re.fullmatch(
                    r'(?:(?:protected|private)\s+)?string\s+m_Key\s*(?:=\s*""\s*)?;',
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

        # 5d (F02-H6): .key solo dentro de LoadConfig(), y solo asignado a m_Key o comparado con ""
        for m in dot_key_re.finditer(code_no_str):
            total_dot_key += 1
            lineno = _line_no(code_no_str, m.start())
            if not _in_spans(m.start(), loadconfig_body_spans):
                violations.append(f"{rel}:{lineno}: acceso .key fuera de LoadConfig()")
                continue
            b_start, b_end = next(
                (bs, be) for bs, be in loadconfig_body_spans if bs <= m.start() < be
            )
            before_full = code_with_str[b_start : m.start()]
            after_full = code_with_str[m.end() : b_end]
            obj_m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", before_full)
            if not obj_m:
                violations.append(f"{rel}:{lineno}: acceso .key sin receptor valido")
                continue
            before_obj = before_full[: obj_m.start()]
            is_assign_m_key = bool(
                re.search(r"(?:^|[;{}])\s*(?:this\s*\.\s*)?m_Key\s*=(?!=)\s*$", before_obj)
                and re.match(r"^\s*;", after_full)
            )
            is_cmp_empty = bool(
                (
                    re.match(r'^\s*(?:==|!=)\s*""', after_full)
                    and not re.search(r"(?<![=!<>])=(?!=)\s*$", before_obj)
                )
                or re.search(r'""\s*(?:==|!=)\s*$', before_obj)
            )
            if not (is_assign_m_key or is_cmp_empty):
                violations.append(
                    f"{rel}:{lineno}: .key solo puede asignarse a m_Key o compararse con \"\": {lines_with_str[lineno - 1].strip()!r}"
                )

        # 5e (F02-H6): Analisis de flujo de datos de variables DSBX_QA_Config dentro de LoadConfig()
        for b_start, b_end in loadconfig_body_spans:
            lc_no_str = code_no_str[b_start:b_end]
            lc_with_str = code_with_str[b_start:b_end]

            # Localizar variables locales DSBX_QA_Config
            cfg_vars = set()
            for decl_m in re.finditer(
                r"\b(?:(?:ref|autoptr)\s+)?DSBX_QA_Config\s+([A-Za-z_][A-Za-z0-9_]*)\b",
                lc_no_str,
            ):
                cfg_vars.add(decl_m.group(1))
            for lf_m in loadfile_re.finditer(lc_no_str):
                op_idx = lf_m.end() - 1
                cl_idx = _find_matching_paren(lc_no_str, op_idx)
                if cl_idx != -1:
                    parts = [p.strip() for p in lc_no_str[op_idx + 1 : cl_idx].split(",")]
                    if len(parts) == 3 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parts[1]):
                        cfg_vars.add(parts[1])

            for cfg_var in sorted(cfg_vars):
                var_re = re.compile(rf"(?<![A-Za-z0-9_.]){re.escape(cfg_var)}(?![A-Za-z0-9_])")
                for vm in var_re.finditer(lc_no_str):
                    abs_pos = b_start + vm.start()
                    lineno = _line_no(code_no_str, abs_pos)
                    line_s = lines_with_str[lineno - 1].strip()
                    after = lc_no_str[vm.end() :].lstrip()

                    # Caso 1: declaracion o inicializacion local de cfg_var
                    if re.fullmatch(
                        rf"(?:(?:(?:ref|autoptr)\s+)?DSBX_QA_Config\s+)?{re.escape(cfg_var)}\s*(?:=\s*(?:null|new\s+DSBX_QA_Config\s*(?:\(\s*\))?))?\s*;",
                        line_s,
                    ):
                        continue

                    # Caso 2: 2o argumento de LoadFile(path, cfg_var, err)
                    in_loadfile_arg2 = False
                    for lf_m in loadfile_re.finditer(lc_no_str):
                        op_idx = lf_m.end() - 1
                        cl_idx = _find_matching_paren(lc_no_str, op_idx)
                        if cl_idx != -1 and op_idx < vm.start() < cl_idx:
                            spans = _split_top_level_spans(lc_no_str, op_idx + 1, cl_idx, sep=",")
                            if (
                                len(spans) == 3
                                and spans[1][0] <= vm.start() < spans[1][1]
                                and lc_no_str[spans[1][0] : spans[1][1]].strip() == cfg_var
                            ):
                                in_loadfile_arg2 = True
                                break
                    if in_loadfile_arg2:
                        continue

                    # Caso 3: acceso a campo cfg.<member>
                    if after.startswith("."):
                        mem_m = re.match(r"^\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*(.*)", after, re.DOTALL)
                        if not mem_m:
                            violations.append(
                                f"{rel}:{lineno}: acceso invalido sobre {cfg_var!r}: {line_s!r}"
                            )
                            continue
                        field_name = mem_m.group(1)
                        rest_after_field = mem_m.group(2)
                        if field_name not in ALLOWED_CFG_FIELDS:
                            violations.append(
                                f"{rel}:{lineno}: de {cfg_var!r} solo se pueden leer {sorted(ALLOWED_CFG_FIELDS)}, accedido .{field_name}"
                            )
                            continue
                        if rest_after_field.startswith("("):
                            violations.append(
                                f"{rel}:{lineno}: llamada de metodo no permitida sobre {cfg_var}.{field_name}"
                            )
                            continue
                        if re.match(r"^=(?!=)", rest_after_field):
                            violations.append(
                                f"{rel}:{lineno}: escritura no permitida en {cfg_var}.{field_name}"
                            )
                            continue
                        continue

                    # Caso 4: comprobacion de nulo (!cfg, cfg == null, cfg != null, if (cfg))
                    before = lc_no_str[: vm.start()].rstrip()
                    if (
                        before.endswith("!")
                        or re.match(r"^(?:==|!=)\s*null\b", after)
                        or re.search(r"\bnull\s*(?:==|!=)\s*$", before)
                        or (
                            re.search(r"(?:\bif\s*\(|&&|\|\|)\s*$", before)
                            and re.match(r"^(?:\)|&&|\|\|)", after)
                        )
                    ):
                        continue

                    violations.append(
                        f"{rel}:{lineno}: el objeto DSBX_QA_Config {cfg_var!r} no puede copiarse a un alias, serializarse ni pasarse a funciones salvo LoadFile: {line_s!r}"
                    )

            # 5d-bis: dentro de LoadConfig(), cada llamada a Log( lleva solo un literal de texto
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

        # 5f (F02-H6): KeyQuery() solo puede aparecer dentro del 2o argumento (request) de ctx.GET(cb, request) o ctx.POST(cb, request, data)
        http_calls = _find_http_get_post_calls(code_no_str)
        for hc in http_calls:
            expected_arity = 2 if hc["method"] == "GET" else 3
            lineno = _line_no(code_no_str, hc["call_span"][0])
            if len(hc["arg_spans"]) != expected_arity:
                violations.append(
                    f"{rel}:{lineno}: llamada .{hc['method']}() debe tener {expected_arity} argumentos (cb, request{', data' if expected_arity == 3 else ''}), tiene {len(hc['arg_spans'])}"
                )

        for m in key_query_re.finditer(code_no_str):
            if _in_spans(m.start(), keyquery_header_spans):
                continue
            total_keyquery_calls += 1
            lineno = _line_no(code_no_str, m.start())
            if _in_spans(m.start(), keyquery_body_spans):
                violations.append(f"{rel}:{lineno}: KeyQuery() no puede invocarse dentro de KeyQuery()")
                continue

            # Verificar que es una llamada KeyQuery() sin argumentos
            call_m = re.match(r"^KeyQuery\s*\(\s*\)", code_no_str[m.start() :])
            if not call_m:
                violations.append(f"{rel}:{lineno}: KeyQuery debe invocarse como KeyQuery()")
                continue
            kq_start = m.start()
            kq_end = m.start() + call_m.end()

            enclosing_http = [
                hc
                for hc in http_calls
                if hc["paren_span"][0] < kq_start and kq_end <= hc["paren_span"][1]
            ]
            if not enclosing_http:
                violations.append(
                    f"{rel}:{lineno}: KeyQuery() fuera de una llamada ctx.GET(cb, request) o ctx.POST(cb, request, data)"
                )
                continue

            hc = enclosing_http[-1]
            expected_arity = 2 if hc["method"] == "GET" else 3
            if len(hc["arg_spans"]) != expected_arity:
                violations.append(
                    f"{rel}:{lineno}: KeyQuery() dentro de .{hc['method']}() con aridad invalida ({len(hc['arg_spans'])})"
                )
                continue

            # 5h: el receptor tiene que estar declarado RestContext en su ambito efectivo (no un envoltorio
            # con GET/POST propio); una declaracion homonima en otra clase no cuenta.
            recv_txt = re.sub(r"\s+", "", code_no_directives[hc["call_span"][0] : hc["paren_span"][0]])
            recv_id = recv_txt.rsplit(".", 1)[0]
            if recv_id.startswith("this."):
                recv_id = recv_id[len("this.") :]
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", recv_id):
                violations.append(
                    f"{rel}:{lineno}: KeyQuery() en .{hc['method']}() sobre un receptor no identificable ({recv_txt!r})"
                )
                continue
            recv_ok, recv_reason = _receiver_is_restcontext(code_no_directives, hc["call_span"][0], recv_id)
            if not recv_ok:
                violations.append(
                    f"{rel}:{lineno}: KeyQuery() en .{hc['method']}() sobre {recv_id!r}, que no es una variable RestContext declarada ({recv_reason})"
                )
                continue

            req_start, req_end = hc["arg_spans"][1]
            if not (req_start <= kq_start and kq_end <= req_end):
                arg_idx = next(
                    (
                        i
                        for i, (a_s, a_e) in enumerate(hc["arg_spans"])
                        if a_s <= kq_start and kq_end <= a_e
                    ),
                    -1,
                )
                arg_label = (
                    "cb (1er argumento)"
                    if arg_idx == 0
                    else ("data (3er argumento)" if arg_idx == 2 else f"argumento {arg_idx + 1}")
                )
                violations.append(
                    f"{rel}:{lineno}: KeyQuery() en {arg_label} de .{hc['method']}(); solo se permite en el 2o argumento (request)"
                )
                continue

            # Verificar que dentro del argumento request, KeyQuery() no se pasa a otra funcion ni se asigna
            req_sub = code_no_str[req_start:req_end]
            rel_kq_start = kq_start - req_start
            rel_kq_end = kq_end - req_start
            nested_fn_violation = False
            for fn_m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", req_sub):
                fn_open = fn_m.end() - 1
                fn_close = _find_matching_paren(req_sub, fn_open)
                if fn_close != -1 and fn_open < rel_kq_start and rel_kq_end <= fn_close:
                    violations.append(
                        f"{rel}:{lineno}: KeyQuery() pasado a la funcion {fn_m.group(1)}() dentro de request"
                    )
                    nested_fn_violation = True
                    break
            if nested_fn_violation:
                continue
            if re.search(r"(?<![=!<>])=(?!=)", req_sub):
                violations.append(
                    f"{rel}:{lineno}: asignacion no permitida en la expresion request que contiene KeyQuery()"
                )

        # 5g: la variable de error de LoadFile solo aparece en su declaracion y en LoadFile
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
                if open_p < occ.start() < close_p:
                    lf_count += 1
                    if log_call_re.search(lines_no_str[occ_line - 1]):
                        violations.append(
                            f"{rel}:{occ_line}: la linea de LoadFile contiene Log()"
                        )
                    continue
                decl_line = lines_with_str[occ_line - 1].strip()
                if re.fullmatch(
                    rf'string\s+{re.escape(err_var)}\s*(?:=\s*""\s*)?;', decl_line
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
    """§6.1(6): HelloBody() contiene en orden \"proto\":\"qa0\", \"peer\":\" , \"inst\":\" , \"build\":\" , \"probe_ver\":\"dsbx-qa1+ y DSBX_QA_STAMP."""
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
    """§6.1(7): Literales de dup, #ifdef DIAG_DEVELOPER con diag/retail, DSBX_QA_RPC_CAM >= 1000000, Send(...) y Event_OnRPC Insert/Remove."""
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
        violations.append("Falta bloque #ifdef DIAG_DEVELOPER ... #else ... #endif")
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
    """§6.1(8): Todos los ficheros de la sonda estan en UTF-8 sin BOM y solo con LF."""
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


def check_9_tick_and_wire_cap(probe_dir):
    """§6.1(9): Tick(float timeslice), DSBX_QA_WIRE_CAP == wire.WIRE_CAP (>= 1024), .Length() tras WriteToString y "result_too_large"."""
    probe_dir = Path(probe_dir)
    violations = []

    wire_cap = _read_python_wire_cap()
    if wire_cap is None:
        violations.append(f"qa/wire.py: no se pudo leer WIRE_CAP de {WIRE_PY_PATH}")
    elif wire_cap < 1024:
        violations.append(f"qa/wire.py: WIRE_CAP debe ser >= 1024, vale {wire_cap}")

    mission_path = probe_dir / "scripts/5_Mission/DSBX_QA_Mission.c"
    if not mission_path.is_file():
        violations.append("scripts/5_Mission/DSBX_QA_Mission.c: fichero ausente")
    else:
        m_text = mission_path.read_text(encoding="utf-8", errors="replace")
        m_no_str = _strip_comments(m_text, blank_strings=True)
        on_update_Re = re.compile(
            r"\b(?:override\s+)?void\s+OnUpdate\s*\(\s*float\s+([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\{",
            re.MULTILINE,
        )
        updates = []
        pos = 0
        while pos < len(m_no_str):
            um = on_update_Re.search(m_no_str, pos)
            if not um:
                break
            ob = um.end() - 1
            cb = _find_matching_brace(m_no_str, ob)
            if cb == -1:
                break
            updates.append((um.group(1), m_no_str[ob + 1 : cb]))
            pos = cb + 1

        if len(updates) != 2:
            violations.append(
                f"DSBX_QA_Mission.c: debe tener exactamente 2 OnUpdate(float timeslice), encontrados {len(updates)}"
            )
        for idx, (param_name, u_body) in enumerate(updates, 1):
            if not re.search(rf"\.\s*Tick\s*\(\s*{re.escape(param_name)}\s*\)", u_body):
                violations.append(
                    f"DSBX_QA_Mission.c: OnUpdate #{idx} no llama a .Tick({param_name})"
                )
        if re.search(r"\.\s*Tick\s*\(\s*\)", m_no_str):
            violations.append("DSBX_QA_Mission.c: contiene llamada prohibida .Tick() sin timeslice")

    probe_path = probe_dir / "scripts/5_Mission/DSBX_QA_Probe.c"
    if not probe_path.is_file():
        violations.append("scripts/5_Mission/DSBX_QA_Probe.c: fichero ausente")
    else:
        p_text = probe_path.read_text(encoding="utf-8", errors="replace")
        p_with_str = _strip_comments(p_text, blank_strings=False)
        p_no_str = _strip_comments(p_text, blank_strings=True)

        if not re.search(r"\bvoid\s+Tick\s*\(\s*float\b", p_no_str):
            violations.append("DSBX_QA_Probe.c: falta declaracion 'void Tick(float ...)'")
        if re.search(r"\bvoid\s+Tick\s*\(\s*\)", p_no_str) or re.search(r"(?<![A-Za-z0-9_])Tick\s*\(\s*\)", p_no_str):
            violations.append("DSBX_QA_Probe.c: contiene Tick() sin argumento float")

        cap_defs = list(
            re.finditer(
                r"\b(?:(?:static|const)\s+)*int\s+DSBX_QA_WIRE_CAP\s*=\s*([+-]?\d+)\s*;",
                p_no_str,
            )
        )
        if len(cap_defs) != 1:
            violations.append(
                f"DSBX_QA_Probe.c: DSBX_QA_WIRE_CAP debe definirse exactamente 1 vez, encontradas {len(cap_defs)}"
            )
        else:
            c_cap = int(cap_defs[0].group(1))
            if c_cap < 1024:
                violations.append(
                    f"DSBX_QA_Probe.c: DSBX_QA_WIRE_CAP debe ser >= 1024, vale {c_cap}"
                )
            if wire_cap is not None and c_cap != wire_cap:
                violations.append(
                    f"DSBX_QA_Probe.c: DSBX_QA_WIRE_CAP ({c_cap}) no coincide con wire.WIRE_CAP ({wire_cap})"
                )

        wts_m = re.search(r"\bWriteToString\s*\(", p_no_str)
        if not wts_m:
            violations.append("DSBX_QA_Probe.c: falta llamada a WriteToString(")
        else:
            len_m = re.search(r"\.\s*Length\s*\(\s*\)", p_no_str[wts_m.end() :])
            if not len_m:
                violations.append("DSBX_QA_Probe.c: no mide .Length() tras WriteToString")

        if '"result_too_large"' not in p_with_str:
            violations.append('DSBX_QA_Probe.c: falta el literal "result_too_large"')

    return violations


def check_10_extensions_and_prefixes(probe_dir):
    """§6.1(10) y Encargo §5.3: DSBX_QA_Ext, DSBX_QA_JobMgr, registro/ciclo de las 9 extensiones y prefijos de literales."""
    probe_dir = Path(probe_dir)
    violations = []

    jobs_path = probe_dir / "scripts/5_Mission/DSBX_QA_Jobs.c"
    if not jobs_path.is_file():
        violations.append("scripts/5_Mission/DSBX_QA_Jobs.c: fichero ausente")
    else:
        j_text = jobs_path.read_text(encoding="utf-8", errors="replace")
        j_no_str = _strip_comments(j_text, blank_strings=True)
        j_blocks = {name: (bs, be) for name, _, bs, be in _extract_named_blocks(j_no_str, "class")}

        if "DSBX_QA_Ext" not in j_blocks:
            violations.append("DSBX_QA_Jobs.c: falta class DSBX_QA_Ext")
        else:
            bs, be = j_blocks["DSBX_QA_Ext"]
            ext_body = j_no_str[bs:be]
            for mname in EXT_REQUIRED_METHODS:
                if not re.search(rf"\b(?:void|bool)\s+{re.escape(mname)}\s*\(", ext_body):
                    violations.append(f"DSBX_QA_Jobs.c: DSBX_QA_Ext sin metodo {mname}()")

        if "DSBX_QA_JobMgr" not in j_blocks:
            violations.append("DSBX_QA_Jobs.c: falta class DSBX_QA_JobMgr")
        else:
            bs, be = j_blocks["DSBX_QA_JobMgr"]
            mgr_body = j_no_str[bs:be]
            for mname in JOBMGR_REQUIRED_METHODS:
                if not re.search(rf"\b(?:void|bool|string)\s+{re.escape(mname)}\s*\(", mgr_body):
                    violations.append(f"DSBX_QA_Jobs.c: DSBX_QA_JobMgr sin metodo {mname}()")

        if not re.search(r"\.\s*OnJobEnd\s*\(", j_no_str):
            violations.append("DSBX_QA_Jobs.c: no invoca .OnJobEnd(")

    probe_path = probe_dir / "scripts/5_Mission/DSBX_QA_Probe.c"
    if not probe_path.is_file():
        violations.append("scripts/5_Mission/DSBX_QA_Probe.c: fichero ausente")
    else:
        p_text = probe_path.read_text(encoding="utf-8", errors="replace")
        p_no_str = _strip_comments(p_text, blank_strings=True)

        last_pos = -1
        for _, cls_name, _, _, _ in EXTENSION_SPECS:
            inst_m = re.search(rf"\bnew\s+{re.escape(cls_name)}\b", p_no_str[last_pos + 1 if last_pos >= 0 else 0 :])
            if not inst_m:
                if re.search(rf"\bnew\s+{re.escape(cls_name)}\b", p_no_str):
                    violations.append(
                        f"DSBX_QA_Probe.c: {cls_name} no se instancia en el orden exigido de §4.1"
                    )
                else:
                    violations.append(f"DSBX_QA_Probe.c: no instancia {cls_name}")
            else:
                last_pos = (last_pos + 1 if last_pos >= 0 else 0) + inst_m.start()

        for hook in ("Init", "Handles", "OnStartOp", "OnTick", "OnRpc", "OnShutdown"):
            if not re.search(rf"\.\s*{hook}\s*\(", p_no_str):
                violations.append(f"DSBX_QA_Probe.c: no invoca .{hook}(")

    for rel, path in _iter_c_files(probe_dir):
        ext_name = _classify_extension_c_file(rel)
        if ext_name is None:
            continue
        _, expected_cls, own_prefix, _, _ = EXTENSION_BY_NAME[ext_name]
        text = path.read_text(encoding="utf-8", errors="replace")
        code_with_str = _strip_comments(text, blank_strings=False)
        code_no_str = _strip_comments(text, blank_strings=True)

        if rel == f"scripts/5_Mission/{expected_cls}.c":
            if not re.search(
                rf"\bclass\s+{re.escape(expected_cls)}\s*(?::|extends)\s*DSBX_QA_Ext\b",
                code_no_str,
            ):
                violations.append(
                    f"{rel}: falta 'class {expected_cls} : DSBX_QA_Ext'"
                )

        forbidden_prefixes = [p for p in ALL_EXT_PREFIXES if p != own_prefix] + ["job_"]
        for lit_offset, lit_val in _extract_c_string_literals(code_with_str):
            for fp in forbidden_prefixes:
                if lit_val.startswith(fp):
                    lineno = _line_no(code_with_str, lit_offset)
                    violations.append(
                        f"{rel}:{lineno}: literal {lit_val!r} empieza por prefijo prohibido {fp!r} (solo se permite {own_prefix!r})"
                    )

    return violations


def check_11_rpc_ranges(probe_dir):
    """§6.1(11): Toda constante int DSBX_QA_RPC_* en DSBX_QA_X_<Name>[_<algo>].c cae en su bloque de 10 ids y DSBX_QA_X_Base.c define DSBX_QA_RPC_BASE_PING = 26102880."""
    probe_dir = Path(probe_dir)
    violations = []
    rpc_decl_re = re.compile(
        r"\b(?:(?:static|const)\s+)*int\s+(DSBX_QA_RPC_[A-Za-z0-9_]*)\s*=\s*([^;]+);"
    )

    found_base_ping = False
    base_file_seen = False

    for rel, path in _iter_c_files(probe_dir):
        ext_name = _classify_extension_c_file(rel)
        if ext_name is None:
            continue
        _, _, _, lo, hi = EXTENSION_BY_NAME[ext_name]
        text = path.read_text(encoding="utf-8", errors="replace")
        code_no_str = _strip_comments(text, blank_strings=True)

        if rel == "scripts/5_Mission/DSBX_QA_X_Base.c":
            base_file_seen = True

        for m in rpc_decl_re.finditer(code_no_str):
            const_name = m.group(1)
            raw_val = m.group(2).strip()
            lineno = _line_no(code_no_str, m.start())
            if not re.fullmatch(r"[+-]?\d+", raw_val):
                violations.append(
                    f"{rel}:{lineno}: {const_name} debe tener un literal entero, recibido {raw_val!r}"
                )
                continue
            val = int(raw_val)
            if not (lo <= val <= hi):
                violations.append(
                    f"{rel}:{lineno}: {const_name} = {val} fuera del rango [{lo}, {hi}] de {ext_name}"
                )
            if (
                rel == "scripts/5_Mission/DSBX_QA_X_Base.c"
                and const_name == "DSBX_QA_RPC_BASE_PING"
                and val == 26102880
            ):
                found_base_ping = True

    if not base_file_seen:
        violations.append("scripts/5_Mission/DSBX_QA_X_Base.c: fichero ausente")
    elif not found_base_ping:
        violations.append(
            "scripts/5_Mission/DSBX_QA_X_Base.c: falta DSBX_QA_RPC_BASE_PING = 26102880"
        )

    return violations


def _resolve_qa_dir_for_check12(probe_dir):
    probe_dir = Path(probe_dir)
    if (probe_dir / "qa").is_dir():
        return probe_dir / "qa"
    if list(probe_dir.glob("*_eval.py")):
        return probe_dir
    resolved = probe_dir.resolve()
    if resolved.parent.name == "probe" and resolved.parents[1].is_dir():
        return resolved.parents[1]
    return QA_DIR


def _extract_mutant_names_from_file(mutants_py_path):
    text = mutants_py_path.read_text(encoding="utf-8", errors="replace")
    names = set()
    try:
        tree = ast.parse(text, filename=str(mutants_py_path))
        for node in ast.walk(tree):
            value_node = None
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "EXPECTED_MUTANTS" for t in node.targets):
                    value_node = node.value
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "EXPECTED_MUTANTS":
                    value_node = node.value
            if isinstance(value_node, ast.Dict):
                for k in value_node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        names.add(k.value)
    except SyntaxError:
        pass
    return sorted(names)


def check_12_blind_evaluators(probe_dir):
    """§6.1(12): Ningun qa/*_eval.py contiene qa_fault, "faults", "mut-", --fault, injection.json, part.json, EXPECTED_MUTANTS ni nombres de mutante de qa/*_mutants.py."""
    qa_dir = _resolve_qa_dir_for_check12(probe_dir)
    eval_files = sorted(qa_dir.glob("*_eval.py"))
    if not eval_files:
        return [f"{qa_dir}: no se encontraron ficheros *_eval.py"]

    mutant_names = set()
    for mut_path in sorted(qa_dir.glob("*_mutants.py")):
        mutant_names.update(_extract_mutant_names_from_file(mut_path))

    forbidden_checks = [
        ("qa_fault", re.compile(r"qa_fault")),
        ('"faults"', re.compile(r"""["']faults["']""")),
        ('"mut-"', re.compile(r"""["']mut-""")),
        ("--fault", re.compile(r"--fault")),
        ("injection.json", re.compile(r"injection\.json")),
        ("part.json", re.compile(r"part\.json")),
        ("EXPECTED_MUTANTS", re.compile(r"\bEXPECTED_MUTANTS\b")),
    ]
    for mname in sorted(mutant_names):
        forbidden_checks.append(
            (
                f"mutante {mname!r}",
                re.compile(rf"(?<![A-Za-z0-9_]){re.escape(mname)}(?![A-Za-z0-9_])"),
            )
        )

    violations = []
    for eval_path in eval_files:
        text = eval_path.read_text(encoding="utf-8", errors="replace")
        rel = eval_path.name
        for label, pat in forbidden_checks:
            for m in pat.finditer(text):
                lineno = _line_no(text, m.start())
                violations.append(f"qa/{rel}:{lineno}: evaluador contiene token prohibido {label}")

    return violations


def check_13_ordered_remove(probe_dir):
    """§14 F02-H2 y Encargo §5.1: Prohibe cualquier .Remove( sobre m_CacheOrder, m_RpcLog, m_PingLog y m_EmitLog en toda la sonda (.RemoveOrdered( permitido)."""
    c_files = _iter_c_files(probe_dir)
    if not c_files:
        return ["No se encontraron ficheros .c en la sonda"]

    violations = []
    forbidden_remove_re = re.compile(
        r"(?<![A-Za-z0-9_])(m_CacheOrder|m_RpcLog|m_PingLog|m_EmitLog)\s*\.\s*Remove\s*\("
    )
    for rel, path in c_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        code_no_str = _strip_comments(text, blank_strings=True)
        for m in forbidden_remove_re.finditer(code_no_str):
            lineno = _line_no(code_no_str, m.start())
            violations.append(
                f"{rel}:{lineno}: llamada prohibida {m.group(1)}.Remove(; debe usar RemoveOrdered"
            )

    return violations


def check_14_explicit_deadman(probe_dir):
    """§14.0 y Encargo §5.2: StartJob declara 9 parametros con 'string deadman' al final sin valor por defecto y toda llamada pasa los 9 argumentos."""
    probe_dir = Path(probe_dir)
    violations = []

    jobs_path = probe_dir / "scripts/5_Mission/DSBX_QA_Jobs.c"
    if not jobs_path.is_file():
        return ["scripts/5_Mission/DSBX_QA_Jobs.c: fichero ausente"]

    j_text = jobs_path.read_text(encoding="utf-8", errors="replace")
    j_with_str = _strip_comments(j_text, blank_strings=False)
    j_no_str = _strip_comments(j_text, blank_strings=True)

    decl_re = re.compile(r"\bstring\s+StartJob\s*\(")
    decl_matches = list(decl_re.finditer(j_no_str))
    if len(decl_matches) != 1:
        violations.append(
            f"DSBX_QA_Jobs.c: se esperaba 1 declaracion 'string StartJob(...)', encontradas {len(decl_matches)}"
        )
    else:
        dm = decl_matches[0]
        open_p = dm.end() - 1
        close_p = _find_matching_paren(j_no_str, open_p)
        lineno = _line_no(j_no_str, dm.start())
        if close_p == -1:
            violations.append(f"DSBX_QA_Jobs.c:{lineno}: StartJob( sin parentesis de cierre")
        else:
            param_spans = _split_top_level_spans(j_no_str, open_p + 1, close_p, sep=",")
            if len(param_spans) != 9:
                violations.append(
                    f"DSBX_QA_Jobs.c:{lineno}: StartJob debe declarar 9 parametros, tiene {len(param_spans)}"
                )
            else:
                p9_raw = j_with_str[param_spans[8][0] : param_spans[8][1]].strip()
                if "=" in p9_raw:
                    violations.append(
                        f"DSBX_QA_Jobs.c:{lineno}: el 9o parametro 'deadman' de StartJob no puede tener valor por defecto: {p9_raw!r}"
                    )
                if not re.fullmatch(r"string\s+deadman", _normalize_type(p9_raw)):
                    violations.append(
                        f"DSBX_QA_Jobs.c:{lineno}: el 9o parametro de StartJob debe ser 'string deadman', recibido {p9_raw!r}"
                    )

    total_calls = 0
    call_re = re.compile(r"(?<![A-Za-z0-9_])StartJob\s*\(")
    for rel, path in _iter_c_files(probe_dir):
        text = path.read_text(encoding="utf-8", errors="replace")
        code_no_str = _strip_comments(text, blank_strings=True)
        for m in call_re.finditer(code_no_str):
            before = code_no_str[: m.start()].rstrip()
            if re.search(r"\b(?:void|bool|string|int|float)$", before):
                continue
            total_calls += 1
            open_p = m.end() - 1
            close_p = _find_matching_paren(code_no_str, open_p)
            lineno = _line_no(code_no_str, m.start())
            if close_p == -1:
                violations.append(f"{rel}:{lineno}: llamada StartJob( sin parentesis de cierre")
                continue
            arg_spans = _split_top_level_spans(code_no_str, open_p + 1, close_p, sep=",")
            non_empty_args = [
                code_no_str[s:e].strip() for s, e in arg_spans if code_no_str[s:e].strip()
            ]
            if len(arg_spans) != 9 or len(non_empty_args) != 9:
                violations.append(
                    f"{rel}:{lineno}: toda llamada a StartJob( debe pasar los 9 argumentos explicitos (incluyendo deadman), pasa {len(non_empty_args)}"
                )

    if total_calls < 1:
        violations.append("No se encontraron llamadas a StartJob( en la sonda")

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
    check_9_tick_and_wire_cap,
    check_10_extensions_and_prefixes,
    check_11_rpc_ranges,
    check_12_blind_evaluators,
    check_13_ordered_remove,
    check_14_explicit_deadman,
)


def run_all_checks(probe_dir):
    violations = []
    for fn in ALL_CHECKS:
        violations.extend(fn(probe_dir))
    return violations


# ---------------------------------------------------------------------------
# Fixture sintetica minima positiva (§6.1 y §14)
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
        dependencies[] = {"World", "Mission"};
        class defs
        {
            class worldScriptModule
            {
                value = "";
                files[] = {"DayZSandbox_QA/scripts/4_World"};
            };
            class missionScriptModule
            {
                value = "";
                files[] = {"DayZSandbox_QA/scripts/5_Mission"};
            };
        };
    };
};
"""

SYNTHETIC_STAMP_C = 'const string DSBX_QA_STAMP = "unstamped";\n'

SYNTHETIC_W_ACTOR_C = """\
class DSBX_QA_W_Actor : Managed
{
}
"""

SYNTHETIC_MESSAGES_C = """\
class DSBX_QA_Config
{
    string url;
    string key;
    int retry_ms;
    int callback_budget;
}

class DSBX_QA_HelloResp
{
    bool ok;
    int lease_ms;
}

class DSBX_QA_AckResp
{
    bool ok;
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
    ref array<string> sk;
    ref array<string> sv;
    ref array<string> nk;
    ref array<float> nv;
    ref array<string> ncol;
    ref array<float> ncell;
    ref array<string> scol;
    ref array<string> scell;
    int rows;
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
    ref array<string> sk;
    ref array<string> sv;
    ref array<string> nk;
    ref array<float> nv;
    ref array<string> ncol;
    ref array<float> ncell;
    ref array<string> scol;
    ref array<string> scell;
    int rows;

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
        sk = new array<string>();
        sv = new array<string>();
        nk = new array<string>();
        nv = new array<float>();
        ncol = new array<string>();
        ncell = new array<float>();
        scol = new array<string>();
        scell = new array<string>();
        rows = 0;
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

SYNTHETIC_JOBS_C = """\
class DSBX_QA_Ext : Managed
{
    void Init(DSBX_QA_Probe probe) {}
    bool Handles(string verb, string role) { return false; }
    void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res) {}
    void OnTick(float timeslice) {}
    void OnJobEnd(string job_id, string state, string reason) {}
    void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx) {}
    void OnShutdown() {}
}

class DSBX_QA_Job : Managed
{
    DSBX_QA_Ext owner;
    string job_id;
    string state;
    string reason;
    string resource;
    string deadman;
}

class DSBX_QA_JobMgr : Managed
{
    string StartJob(DSBX_QA_Ext owner, string job_id, string resource, array<string> ncol, array<string> scol, int page_size, int max_rows, float max_duration_ms, string deadman)
    {
        if (deadman != "stop" && deadman != "continue")
        {
            return "bad_deadman";
        }
        return "";
    }

    void FillStartRead(DSBX_QA_Read read, string job_id, string resource)
    {
    }

    bool AppendRow(string job_id, array<float> nvals, array<string> svals)
    {
        return true;
    }

    string GetState(string job_id)
    {
        return "";
    }

    bool EndJob(string job_id, string state, string reason)
    {
        DSBX_QA_Ext owner;
        if (owner)
        {
            owner.OnJobEnd(job_id, state, reason);
        }
        return true;
    }
}
"""


def _build_synthetic_probe_c(wire_cap):
    return f"""\
static const int DSBX_QA_RPC_CAM = 26102701;
const int DSBX_QA_WIRE_CAP = {wire_cap};

class DSBX_QA_Callback : RestCallback
{{
    DSBX_QA_Probe m_Probe;
}}

class DSBX_QA_Probe : Managed
{{
    string m_Role;
    string m_Inst;
    string m_Build;
    string m_Url;
    string m_Key;
    int m_RetryMs;
    int m_CallbackBudget;
    int m_Frame;
    float m_DtSumMs;
    RestContext m_Ctx;
    ref DSBX_QA_JobMgr m_Jobs;
    ref array<ref DSBX_QA_Ext> m_Exts;
    ref array<string> m_CacheOrder;
    ref array<ref DSBX_QA_RpcEntry> m_RpcLog;
    ref array<string> m_EmitLog;

    void DSBX_QA_Probe(string role)
    {{
        m_Role = role;
#ifdef DIAG_DEVELOPER
        m_Build = "diag";
#else
        m_Build = "retail";
#endif
        m_Jobs = new DSBX_QA_JobMgr();
        m_Exts = new array<ref DSBX_QA_Ext>();
        m_Exts.Insert(new DSBX_QA_X_Persist());
        m_Exts.Insert(new DSBX_QA_X_Actor());
        m_Exts.Insert(new DSBX_QA_X_Cam());
        m_Exts.Insert(new DSBX_QA_X_Cot());
        m_Exts.Insert(new DSBX_QA_X_Env());
        m_Exts.Insert(new DSBX_QA_X_Take());
        m_Exts.Insert(new DSBX_QA_X_Perf());
        m_Exts.Insert(new DSBX_QA_X_Map());
        m_Exts.Insert(new DSBX_QA_X_Base());
        for (int i = 0; i < m_Exts.Count(); i++)
        {{
            m_Exts.Get(i).Init(this);
        }}
        DayZGame.Event_OnRPC.Insert(DSBX_QA_Probe.OnAnyRpc);
    }}

    void ~DSBX_QA_Probe()
    {{
        Shutdown();
    }}

    void Shutdown()
    {{
        for (int i = 0; i < m_Exts.Count(); i++)
        {{
            m_Exts.Get(i).OnShutdown();
        }}
        DayZGame.Event_OnRPC.Remove(DSBX_QA_Probe.OnAnyRpc);
    }}

    void Tick(float timeslice)
    {{
        m_Frame++;
        m_DtSumMs += timeslice * 1000.0;
        for (int i = 0; i < m_Exts.Count(); i++)
        {{
            m_Exts.Get(i).OnTick(timeslice);
        }}
    }}

    void EvictOrdered()
    {{
        if (m_CacheOrder.Count() > 1024)
        {{
            m_CacheOrder.RemoveOrdered(0);
        }}
        if (m_RpcLog.Count() > 512)
        {{
            m_RpcLog.RemoveOrdered(0);
        }}
        if (m_EmitLog.Count() > 512)
        {{
            m_EmitLog.RemoveOrdered(0);
        }}
    }}

    void DispatchExt(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
    {{
        for (int i = 0; i < m_Exts.Count(); i++)
        {{
            DSBX_QA_Ext ext = m_Exts.Get(i);
            if (ext.Handles(op.verb, m_Role))
            {{
                ext.OnStartOp(op, args, res);
                return;
            }}
        }}
    }}

    void Log(string msg)
    {{
        Print("[DSBX_QA] " + msg);
    }}

    bool LoadConfig()
    {{
        DSBX_QA_Config cfg;
        string err;
        if (!JsonFileLoader<DSBX_QA_Config>.LoadFile("$profile:dsbx_qa.json", cfg, err))
        {{
            Log("config unreadable");
            return false;
        }}
        if (!cfg || cfg.key == "" || cfg.url.IndexOf("http://127.0.0.1:") != 0)
        {{
            Log("config invalid");
            return false;
        }}
        m_Url = cfg.url;
        m_Key = cfg.key;
        m_RetryMs = cfg.retry_ms;
        m_CallbackBudget = cfg.callback_budget;
        Log("config usable");
        return true;
    }}

    string KeyQuery()
    {{
        return "key=" + m_Key;
    }}

    string HelloBody()
    {{
        return "{{\\"proto\\":\\"qa0\\",\\"peer\\":\\"" + m_Role + "\\",\\"inst\\":\\"" + m_Inst + "\\",\\"build\\":\\"" + m_Build + "\\",\\"probe_ver\\":\\"dsbx-qa1+" + DSBX_QA_STAMP + "\\"}}";
    }}

    void SendHello(DSBX_QA_Callback cb)
    {{
        m_Ctx.POST(cb, "hello?" + KeyQuery(), HelloBody());
    }}

    void SendPoll(DSBX_QA_Callback cb, float tick_s)
    {{
        m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame.ToString() + "&tick_s=" + tick_s.ToString());
    }}

    bool SendResult(DSBX_QA_Result result, DSBX_QA_Callback cb)
    {{
        JsonSerializer js = new JsonSerializer();
        string body;
        js.WriteToString(result, false, body);
        int idx0 = body.IndexOf("\\"dup\\":0");
        int idx1 = body.IndexOf("\\"dup\\":1");
        if (idx0 >= 0)
        {{
            body = body.Substring(0, idx0) + "\\"dup\\":false" + body.Substring(idx0 + 7, body.Length() - (idx0 + 7));
        }}
        else if (idx1 >= 0)
        {{
            body = body.Substring(0, idx1) + "\\"dup\\":true" + body.Substring(idx1 + 7, body.Length() - (idx1 + 7));
        }}
        if (body.Length() > DSBX_QA_WIRE_CAP)
        {{
            result.status = "error";
            result.reason = "result_too_large";
        }}
        m_Ctx.POST(cb, "result?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst, body);
        return true;
    }}

    void SendCamRpc(int seq, string target_inst, array<float> pos, array<float> ypr)
    {{
        ScriptRPC rpc = new ScriptRPC();
        rpc.Write(seq);
        rpc.Write(target_inst);
        rpc.Write(pos);
        rpc.Write(ypr);
        rpc.Send(null, DSBX_QA_RPC_CAM, true, null);
    }}

    static void OnAnyRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
    {{
    }}

    void RouteRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
    {{
        if (rpc_type == DSBX_QA_RPC_CAM)
        {{
            return;
        }}
        if (26102800 <= rpc_type && rpc_type <= 26102889)
        {{
            int idx = (rpc_type - 26102800) / 10;
            m_Exts.Get(idx).OnRpc(sender, target, rpc_type, ctx);
        }}
    }}
}}
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

    override void OnUpdate(float timeslice)
    {
        super.OnUpdate(timeslice);
        if (m_DsbxQaProbe)
        {
            m_DsbxQaProbe.Tick(timeslice);
        }
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

    override void OnUpdate(float timeslice)
    {
        super.OnUpdate(timeslice);
        if (m_DsbxQaProbe)
        {
            m_DsbxQaProbe.Tick(timeslice);
        }
    }
}
"""

SYNTHETIC_X_BASE_C = """\
static const int DSBX_QA_RPC_BASE_PING = 26102880;

class DSBX_QA_X_Base : DSBX_QA_Ext
{
    DSBX_QA_Probe m_Probe;
    ref array<int> m_PingLog;

    override void Init(DSBX_QA_Probe probe)
    {
        m_Probe = probe;
        m_PingLog = new array<int>();
    }

    override bool Handles(string verb, string role)
    {
        return verb == "qa_echo" || verb == "qa_timer_start" || verb == "qa_rpc_ping";
    }

    override void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
    {
        if (op.verb == "qa_timer_start")
        {
            ref array<string> ncol = new array<string>();
            ref array<string> scol = new array<string>();
            m_Probe.m_Jobs.StartJob(this, op.op_id, "qa_timer", ncol, scol, 20, 4096, 900000.0, "continue");
        }
    }

    override void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
    {
        if (rpc_type == DSBX_QA_RPC_BASE_PING)
        {
            if (m_PingLog.Count() >= 512)
            {
                m_PingLog.RemoveOrdered(0);
            }
        }
    }
}
"""

SYNTHETIC_EVAL_PY = """\
def evaluate(part_dir):
    return {"verdict": "PASA", "exit_code": 0, "checks": []}
"""

SYNTHETIC_MUTANTS_PY = """\
EXPECTED_MUTANTS = {
    "ignore_stop": {"expected_exit_code": 1, "must_fail_checks": ["BASE-03"], "allowed_non_pass": {}},
    "freeze_on_wait": {"expected_exit_code": 1, "must_fail_checks": ["BASE-08"], "allowed_non_pass": {}},
    "defer_cleanup": {"expected_exit_code": 1, "must_fail_checks": ["BASE-08"], "allowed_non_pass": {}},
}
"""


def _build_skeleton_ext_c(cls_name):
    return f"""\
class {cls_name} : DSBX_QA_Ext
{{
    override bool Handles(string verb, string role)
    {{
        return false;
    }}
}}
"""


def make_synthetic_files():
    wire_cap = _read_python_wire_cap() or 3500
    files = {
        "$PBOPREFIX$": b"DayZSandbox_QA\n",
        "include.lst": b"*.c\n",
        "config.cpp": SYNTHETIC_CONFIG_CPP.encode("utf-8"),
        "scripts/4_World/DSBX_QA_W_Actor.c": SYNTHETIC_W_ACTOR_C.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Stamp.c": SYNTHETIC_STAMP_C.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Messages.c": SYNTHETIC_MESSAGES_C.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Jobs.c": SYNTHETIC_JOBS_C.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Probe.c": _build_synthetic_probe_c(wire_cap).encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_Mission.c": SYNTHETIC_MISSION_C.encode("utf-8"),
        "scripts/5_Mission/DSBX_QA_X_Base.c": SYNTHETIC_X_BASE_C.encode("utf-8"),
        "qa/f03_base_eval.py": SYNTHETIC_EVAL_PY.encode("utf-8"),
        "qa/f03_base_mutants.py": SYNTHETIC_MUTANTS_PY.encode("utf-8"),
    }
    for name, cls_name, _, _, _ in EXTENSION_SPECS:
        if name == "Base":
            continue
        files[f"scripts/5_Mission/{cls_name}.c"] = _build_skeleton_ext_c(cls_name).encode("utf-8")
    return files


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

    def test_pos_check1_optional_inputs_and_extra_ext_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = make_synthetic_files()
            files["config.cpp"] = files["config.cpp"].replace(
                b'        type = "mod";\n',
                b'        type = "mod";\n        inputs = "DayZSandbox_QA/inputs.xml";\n',
            )
            files["inputs.xml"] = b"<modded_inputs></modded_inputs>\n"
            files["scripts/5_Mission/DSBX_QA_X_Cam_Helper.c"] = b"// helper\n"
            files["scripts/4_World/DSBX_QA_W_Actor_Gesture.c"] = b"// actor helper\n"
            write_probe_tree(tmp, files)
            self.assertEqual(run_all_checks(tmp), [])

    def test_pos_check5_get_and_post_signatures(self):
        # F02-H6: las dos firmas positivas ctx.GET(cb, <expr con KeyQuery()>) y ctx.POST(cb, <expr con KeyQuery()>, data), incluso en varias lineas
        with tempfile.TemporaryDirectory() as tmp:
            files = make_synthetic_files()
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'        m_Ctx.POST(cb, "hello?" + KeyQuery(), HelloBody());',
                b'        m_Ctx.POST(\n            cb,\n            "hello?" + KeyQuery(),\n            HelloBody()\n        );',
            ).replace(
                b'        m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame.ToString() + "&tick_s=" + tick_s.ToString());',
                b'        m_Ctx.GET(\n            cb,\n            "poll?" + KeyQuery() + "&peer=" + m_Role\n        );',
            )
            write_probe_tree(tmp, files)
            self.assertEqual(check_5_key_containment(tmp), [])
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

        # 1c: config.cpp sin World en dependencies[]
        def mut_config_deps(files):
            files["config.cpp"] = files["config.cpp"].replace(
                b'dependencies[] = {"World", "Mission"};',
                b'dependencies[] = {"Mission"};',
            )

        self._assert_mutation_caught_by(mut_config_deps, check_1_mod_files)

        # 1d: DSBX_QA_Stamp.c con sello invalido
        def mut_stamp(files):
            files["scripts/5_Mission/DSBX_QA_Stamp.c"] = b'const string DSBX_QA_STAMP = "invalid_stamp";\n'

        self._assert_mutation_caught_by(mut_stamp, check_1_mod_files)

        # 1e: fichero .c no autorizado
        def mut_extra_c(files):
            files["scripts/5_Mission/DSBX_QA_Unauthorized.c"] = b"// no autorizado\n"

        self._assert_mutation_caught_by(mut_extra_c, check_1_mod_files)

    def test_neg_check2_renamed_json_field(self):
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"int lease_ms;", b"int lease_duration_ms;")

        self._assert_mutation_caught_by(mut, check_2_json_classes)

    def test_neg_check2_extra_member(self):
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"int lease_ms;", b"int lease_ms;\n    int extra_field;")

        self._assert_mutation_caught_by(mut, check_2_json_classes)

    def test_neg_check2_missing_f02_h4_or_h5_fields(self):
        # F02-H4: falta callback_budget en DSBX_QA_Config
        def mut_budget(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"    int callback_budget;\n", b"")

        self._assert_mutation_caught_by(mut_budget, check_2_json_classes)

        # F02-H5: falta DSBX_QA_AckResp
        def mut_ack(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"class DSBX_QA_AckResp\n{\n    bool ok;\n}\n\n", b"")

        self._assert_mutation_caught_by(mut_ack, check_2_json_classes)

    def test_neg_check3_uncreated_ref_in_ctor(self):
        def mut_rpclog(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"        rpc_log = new array<ref DSBX_QA_RpcEntry>();\n", b"")

        self._assert_mutation_caught_by(mut_rpclog, check_3_write_ctors)

        def mut_scell(files):
            files["scripts/5_Mission/DSBX_QA_Messages.c"] = files[
                "scripts/5_Mission/DSBX_QA_Messages.c"
            ].replace(b"        scell = new array<string>();\n", b"")

        self._assert_mutation_caught_by(mut_scell, check_3_write_ctors)

    def test_neg_check4_forbidden_tokens(self):
        def mut_enable_debug(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n        m_Ctx.EnableDebug(true);\n",
            )

        self._assert_mutation_caught_by(mut_enable_debug, check_4_forbidden_tokens)

        def mut_replace(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b'    void SendHello(DSBX_QA_Callback cb)\n    {\n        m_Role.Replace("a", "b");\n',
            )

        self._assert_mutation_caught_by(mut_replace, check_4_forbidden_tokens)

    def test_neg_check5_print_outside_log(self):
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b'    void SendHello(DSBX_QA_Callback cb)\n    {\n        Print("x");\n',
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_log_m_key_outside_allowed(self):
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n        Log(m_Key);\n",
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_member_key_alias(self):
        # F02-H6 negativa 1: un miembro alias de la clave
        def mut_from_cfg_key(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    string m_Key;\n",
                b"    string m_Key;\n    string m_KeyAlias;\n",
            ).replace(
                b"        m_Key = cfg.key;\n",
                b"        m_Key = cfg.key;\n        m_KeyAlias = cfg.key;\n",
            )

        self._assert_mutation_caught_by(mut_from_cfg_key, check_5_key_containment)

        def mut_from_m_key(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    string m_Key;\n",
                b"    string m_Key;\n    string m_KeyAlias;\n",
            ).replace(
                b"        m_Key = cfg.key;\n",
                b"        m_Key = cfg.key;\n        m_KeyAlias = m_Key;\n",
            )

        self._assert_mutation_caught_by(mut_from_m_key, check_5_key_containment)

    def test_neg_check5_member_cfg_serialized_and_logged(self):
        # F02-H6 negativa 2 (V8): un miembro que guarda el cfg entero y luego se serializa y se pasa a Log()
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    string m_Key;\n",
                b"    string m_Key;\n    ref DSBX_QA_Config m_SavedCfg;\n",
            ).replace(
                b"        m_Key = cfg.key;\n",
                b"        m_Key = cfg.key;\n        m_SavedCfg = cfg;\n",
            ).replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n        JsonSerializer js = new JsonSerializer();\n        string s;\n        js.WriteToString(m_SavedCfg, false, s);\n        Log(s);\n",
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_key_query_in_data_or_cb(self):
        # F02-H6 negativa 3: KeyQuery() en el argumento data o en el cb
        def mut_in_data(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'        m_Ctx.POST(cb, "hello?" + KeyQuery(), HelloBody());',
                b'        m_Ctx.POST(cb, "hello", KeyQuery());',
            )

        self._assert_mutation_caught_by(mut_in_data, check_5_key_containment)

        def mut_in_cb(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'        m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame.ToString() + "&tick_s=" + tick_s.ToString());',
                b'        m_Ctx.GET(KeyQuery(), "poll");',
            )

        self._assert_mutation_caught_by(mut_in_cb, check_5_key_containment)

    def test_neg_check5_intermediate_variable(self):
        # F02-H6 negativa 4: una variable intermedia (string q = KeyQuery(); ctx.GET(cb, q)), incluso en la misma linea
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'        m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame.ToString() + "&tick_s=" + tick_s.ToString());',
                b"        string q = KeyQuery(); m_Ctx.GET(cb, q);",
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_key_query_passed_to_other_function(self):
        # F02-H6 negativa 5: KeyQuery() pasado a otra funcion
        def mut_direct(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n",
                b"    void SendHello(DSBX_QA_Callback cb)\n    {\n        Log(KeyQuery());\n",
            )

        self._assert_mutation_caught_by(mut_direct, check_5_key_containment)

        def mut_nested_in_request(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'        m_Ctx.POST(cb, "hello?" + KeyQuery(), HelloBody());',
                b'        m_Ctx.POST(cb, "hello?" + Escape(KeyQuery()), HelloBody());',
            )

        self._assert_mutation_caught_by(mut_nested_in_request, check_5_key_containment)

    def test_neg_check5_wrapper_get_that_logs_the_request(self):
        # H7 de Sol r1: SendPoll llama a un envoltorio con metodo GET propio que registra la peticion (con la clave)
        # y la reenvia al RestContext. KeyQuery() sigue en el 2o argumento, pero el receptor no es RestContext.
        wrapper = (
            b"class DSBX_QA_HttpWrap\n"
            b"{\n"
            b"    DSBX_QA_Probe m_P;\n"
            b"    RestContext m_Inner;\n"
            b"    void GET(DSBX_QA_Callback cb, string request)\n"
            b"    {\n"
            b"        m_P.Log(request);\n"
            b"        m_Inner.GET(cb, request);\n"
            b"    }\n"
            b"}\n\n"
        )

        def mut_wrapper(files):
            src = files["scripts/5_Mission/DSBX_QA_Probe.c"]
            old_call = b'        m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame.ToString() + "&tick_s=" + tick_s.ToString());'
            assert old_call in src
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = wrapper + src.replace(old_call, old_call.replace(b"m_Ctx.GET(", b"m_Wrap.GET("))

        self._assert_mutation_caught_by(mut_wrapper, check_5_key_containment)

        # Solo el metodo GET propio, aunque la llamada siga yendo a m_Ctx: tambien es violacion
        def mut_def_only(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = wrapper + files["scripts/5_Mission/DSBX_QA_Probe.c"]

        self._assert_mutation_caught_by(mut_def_only, check_5_key_containment)

    def test_neg_check5_wrapper_get_hidden_by_directive(self):
        # N3: un metodo GET propio cuya firma y llave estan separadas por directivas vacias en lineas
        # propias (#ifdef DIAG_DEVELOPER / #endif) sigue siendo un metodo propio y debe detectarse.
        wrapper = (
            b"class DSBX_QA_HttpWrapDiag\n"
            b"{\n"
            b"    DSBX_QA_Probe m_P;\n"
            b"    RestContext m_Inner;\n"
            b"    void GET(DSBX_QA_Callback cb, string request)\n"
            b"#ifdef DIAG_DEVELOPER\n"
            b"#endif\n"
            b"    {\n"
            b"        m_P.Log(request);\n"
            b"        m_Inner.GET(cb, request);\n"
            b"    }\n"
            b"}\n\n"
        )

        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = (
                wrapper + files["scripts/5_Mission/DSBX_QA_Probe.c"]
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check5_wrapper_receiver_homonym_in_other_class(self):
        # N3: la clase que hace el poll declara DSBX_QA_Wrap m_Wrap y llama a m_Wrap.GET(...);
        # que otra clase declare RestContext m_Wrap no debe acreditar el receptor: manda el ambito.
        wrapper_c = (
            b"class DSBX_QA_Wrap\n"
            b"{\n"
            b"    RestContext m_Inner;\n"
            b"    void GET(DSBX_QA_Callback cb, string request)\n"
            b"    {\n"
            b"        m_Inner.GET(cb, request);\n"
            b"    }\n"
            b"}\n\n"
            b"class DSBX_QA_OtherHolder\n"
            b"{\n"
            b"    RestContext m_Wrap;\n"
            b"}\n"
        )
        old_call = b'        m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame.ToString() + "&tick_s=" + tick_s.ToString());'

        def mut(files):
            src = files["scripts/5_Mission/DSBX_QA_Probe.c"]
            assert old_call in src
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = src.replace(
                b"    RestContext m_Ctx;\n",
                b"    RestContext m_Ctx;\n    DSBX_QA_Wrap m_Wrap;\n",
            ).replace(old_call, old_call.replace(b"m_Ctx.GET(", b"m_Wrap.GET("))
            files["scripts/4_World/DSBX_QA_W_Actor_Wrap.c"] = wrapper_c

        with tempfile.TemporaryDirectory() as tmp:
            files = make_synthetic_files()
            mut(files)
            write_probe_tree(tmp, files)
            violations = check_5_key_containment(tmp)
            self.assertTrue(
                any("no es una variable RestContext declarada" in v for v in violations),
                f"check_5 debio rechazar el receptor m_Wrap por ambito y devolvio {violations!r}",
            )
            for other_fn in ALL_CHECKS:
                if other_fn is check_5_key_containment:
                    continue
                self.assertEqual(
                    other_fn(tmp),
                    [],
                    f"{other_fn.__name__} debio seguir en [] sobre la mutacion de receptor homonimo",
                )

    def test_neg_check5_log_err_inside_load_config(self):
        def mut(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'            Log("config unreadable");',
                b"            Log(err);",
            )

        self._assert_mutation_caught_by(mut, check_5_key_containment)

    def test_neg_check6_hello_body(self):
        def mut_proto(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'{\\"proto\\":\\"qa0\\"',
                b'{\\"prto\\":\\"qa0\\"',
            )

        self._assert_mutation_caught_by(mut_proto, check_6_hello_body)

        def mut_missing_stamp(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b'\\"probe_ver\\":\\"dsbx-qa1+" + DSBX_QA_STAMP + "\\"}',
                b'\\"probe_ver\\":\\"dsbx-qa0\\"}',
            )

        self._assert_mutation_caught_by(mut_missing_stamp, check_6_hello_body)

    def test_neg_check7_required_pieces(self):
        def mut_remove(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"        DayZGame.Event_OnRPC.Remove(DSBX_QA_Probe.OnAnyRpc);\n",
                b"",
            )

        self._assert_mutation_caught_by(mut_remove, check_7_required_pieces)

        def mut_dup(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(b'\\"dup\\":false', b'\\"dup\\":0')

        self._assert_mutation_caught_by(mut_dup, check_7_required_pieces)

    def test_neg_check8_encoding_and_eol(self):
        def mut_bom(files):
            files["scripts/5_Mission/DSBX_QA_Mission.c"] = (
                b"\xef\xbb\xbf" + files["scripts/5_Mission/DSBX_QA_Mission.c"]
            )

        self._assert_mutation_caught_by(mut_bom, check_8_encoding_and_eol)

        def mut_crlf(files):
            files["$PBOPREFIX$"] = b"DayZSandbox_QA\r\n"

        self._assert_mutation_caught_by(mut_crlf, check_8_encoding_and_eol)

    def test_neg_check9_tick_and_wire_cap(self):
        # 9a: Tick() sin timeslice en DSBX_QA_Mission.c
        def mut_mission_tick(files):
            files["scripts/5_Mission/DSBX_QA_Mission.c"] = files[
                "scripts/5_Mission/DSBX_QA_Mission.c"
            ].replace(b"m_DsbxQaProbe.Tick(timeslice);", b"m_DsbxQaProbe.Tick();")

        self._assert_mutation_caught_by(mut_mission_tick, check_9_tick_and_wire_cap)

        # 9b: DSBX_QA_WIRE_CAP desincronizado respecto a wire.WIRE_CAP
        def mut_wire_cap(files):
            wire_cap = _read_python_wire_cap() or 3500
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                f"const int DSBX_QA_WIRE_CAP = {wire_cap};".encode("utf-8"),
                f"const int DSBX_QA_WIRE_CAP = {wire_cap + 100};".encode("utf-8"),
            )

        self._assert_mutation_caught_by(mut_wire_cap, check_9_tick_and_wire_cap)

        # 9c: falta "result_too_large"
        def mut_result_too_large(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(b'"result_too_large"', b'"too_big"')

        self._assert_mutation_caught_by(mut_result_too_large, check_9_tick_and_wire_cap)

    def test_neg_check10_extensions_and_prefixes(self):
        # 10a: literal con prefijo de otra extension (per_ en DSBX_QA_X_Cam.c)
        def mut_wrong_ext_prefix(files):
            files["scripts/5_Mission/DSBX_QA_X_Cam.c"] = files[
                "scripts/5_Mission/DSBX_QA_X_Cam.c"
            ].replace(
                b"return false;",
                b'return verb == "per_spawn";',
            )

        self._assert_mutation_caught_by(mut_wrong_ext_prefix, check_10_extensions_and_prefixes)

        # 10b: literal con prefijo job_ en una extension
        def mut_job_prefix(files):
            files["scripts/5_Mission/DSBX_QA_X_Base.c"] = files[
                "scripts/5_Mission/DSBX_QA_X_Base.c"
            ].replace(
                b'verb == "qa_echo"',
                b'verb == "job_read"',
            )

        self._assert_mutation_caught_by(mut_job_prefix, check_10_extensions_and_prefixes)

        # 10c: orden de instanciacion de extensiones alterado en DSBX_QA_Probe.c
        def mut_ext_order(files):
            files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                "scripts/5_Mission/DSBX_QA_Probe.c"
            ].replace(
                b"        m_Exts.Insert(new DSBX_QA_X_Persist());\n        m_Exts.Insert(new DSBX_QA_X_Actor());\n",
                b"        m_Exts.Insert(new DSBX_QA_X_Actor());\n        m_Exts.Insert(new DSBX_QA_X_Persist());\n",
            )

        self._assert_mutation_caught_by(mut_ext_order, check_10_extensions_and_prefixes)

    def test_neg_check11_rpc_ranges(self):
        # 11a: constante RPC fuera del bloque de su extension
        def mut_out_of_range(files):
            files["scripts/5_Mission/DSBX_QA_X_Cam.c"] = (
                b"static const int DSBX_QA_RPC_CAM_BAD = 26102805;\n"
                + files["scripts/5_Mission/DSBX_QA_X_Cam.c"]
            )

        self._assert_mutation_caught_by(mut_out_of_range, check_11_rpc_ranges)

        # 11b: falta DSBX_QA_RPC_BASE_PING = 26102880 en DSBX_QA_X_Base.c
        def mut_missing_base_ping(files):
            files["scripts/5_Mission/DSBX_QA_X_Base.c"] = files[
                "scripts/5_Mission/DSBX_QA_X_Base.c"
            ].replace(
                b"static const int DSBX_QA_RPC_BASE_PING = 26102880;",
                b"static const int DSBX_QA_RPC_BASE_PING = 26102881;",
            )

        self._assert_mutation_caught_by(mut_missing_base_ping, check_11_rpc_ranges)

    def test_neg_check12_blind_evaluators(self):
        # 12a: token prohibido part.json / injection.json / qa_fault en *_eval.py
        for token_line in (
            b'    _ = "part.json"\n',
            b'    _ = "injection.json"\n',
            b'    _ = "qa_fault"\n',
            b'    _ = "mut-"\n',
            b"    _ = EXPECTED_MUTANTS\n",
            b'    _ = "defer_cleanup"\n',
        ):
            def mut_eval(files, line=token_line):
                files["qa/f03_base_eval.py"] = files["qa/f03_base_eval.py"] + line

            self._assert_mutation_caught_by(mut_eval, check_12_blind_evaluators)

        # Comprobar tambien que los *_eval.py reales presentes en qa/ cumplen check_12
        self.assertEqual(check_12_blind_evaluators(QA_DIR), [])

    def test_neg_check13_ordered_remove(self):
        # F02-H2: .Remove(0) prohibido sobre m_CacheOrder, m_RpcLog, m_PingLog y m_EmitLog
        for member in ("m_CacheOrder", "m_RpcLog", "m_EmitLog"):
            def mut_probe_remove(files, m=member):
                files["scripts/5_Mission/DSBX_QA_Probe.c"] = files[
                    "scripts/5_Mission/DSBX_QA_Probe.c"
                ].replace(
                    f"{m}.RemoveOrdered(0);".encode("utf-8"),
                    f"{m}.Remove(0);".encode("utf-8"),
                )

            self._assert_mutation_caught_by(mut_probe_remove, check_13_ordered_remove)

        def mut_ping_remove(files):
            files["scripts/5_Mission/DSBX_QA_X_Base.c"] = files[
                "scripts/5_Mission/DSBX_QA_X_Base.c"
            ].replace(
                b"m_PingLog.RemoveOrdered(0);",
                b"m_PingLog.Remove(0);",
            )

        self._assert_mutation_caught_by(mut_ping_remove, check_13_ordered_remove)

    def test_neg_check14_explicit_deadman(self):
        # 14.0a: valor por defecto en deadman en la declaracion de StartJob en DSBX_QA_Jobs.c
        def mut_default_deadman(files):
            files["scripts/5_Mission/DSBX_QA_Jobs.c"] = files[
                "scripts/5_Mission/DSBX_QA_Jobs.c"
            ].replace(
                b"float max_duration_ms, string deadman)",
                b'float max_duration_ms, string deadman = "stop")',
            )

        self._assert_mutation_caught_by(mut_default_deadman, check_14_explicit_deadman)

        # 14.0b: llamada a StartJob con 8 argumentos (omitiendo deadman)
        def mut_call_8_args(files):
            files["scripts/5_Mission/DSBX_QA_X_Base.c"] = files[
                "scripts/5_Mission/DSBX_QA_X_Base.c"
            ].replace(
                b'm_Probe.m_Jobs.StartJob(this, op.op_id, "qa_timer", ncol, scol, 20, 4096, 900000.0, "continue");',
                b'm_Probe.m_Jobs.StartJob(this, op.op_id, "qa_timer", ncol, scol, 20, 4096, 900000.0);',
            )

        self._assert_mutation_caught_by(mut_call_8_args, check_14_explicit_deadman)

    def test_real_probe_zero_violations(self):
        if not REAL_PROBE_DIR.is_dir():
            self.fail(f"Falta el directorio de la sonda real: {REAL_PROBE_DIR}")
        for check_fn in ALL_CHECKS:
            self.assertEqual(
                check_fn(REAL_PROBE_DIR),
                [],
                f"La sonda real tiene violaciones en {check_fn.__name__}",
            )


if __name__ == "__main__":
    unittest.main()
