"""Prueba estatica del mod nucleo DayZSandbox/ (F1b-peers §5.2, reglas M1-M12 y antitautologia X4)."""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from app.backend.bridge import WIRE_CAP

REAL_MOD_DIR = Path(__file__).resolve().parents[3] / "DayZSandbox"

EXPECTED_C_FILES = (
    "scripts/3_Game/DSBX_Const.c",
    "scripts/3_Game/DSBX_Messages.c",
    "scripts/3_Game/DSBX_Wire.c",
    "scripts/3_Game/DSBX_Cache.c",
    "scripts/3_Game/DSBX_World.c",
    "scripts/3_Game/DSBX_Catalog.c",
    "scripts/3_Game/DSBX_Peer.c",
    # F2-partida T3 (brief §4.1): la escena viva.
    "scripts/3_Game/DSBX_Scene.c",
    "scripts/3_Game/DSBX_SceneOps.c",
    "scripts/3_Game/DSBX_SceneWire.c",
    "scripts/5_Mission/DSBX_Mission.c",
)

EXPECTED_REL_FILES = (
    "$PBOPREFIX$",
    "include.lst",
    "config.cpp",
    *EXPECTED_C_FILES,
)

EXPECTED_JSON_CLASSES = {
    "DSBX_PeerConfig": [
        ("string", "url"),
        ("string", "key"),
    ],
    "DSBX_HelloResp": [
        ("bool", "ok"),
        ("string", "session"),
        ("int", "conn"),
        ("int", "lease_ms"),
        ("int", "hold_ms"),
        ("int", "wire_cap"),
    ],
    "DSBX_Args": [
        ("string", "doc_id"),
        ("int", "rev"),
        ("string", "hash"),
    ],
    "DSBX_Order": [
        ("string", "op_id"),
        ("string", "session"),
        ("int", "conn"),
        ("string", "epoch"),
        ("string", "inst"),
        ("string", "verb"),
        ("ref DSBX_Args", "args"),
        ("int", "issued_ms"),
        ("int", "ttl_ms"),
    ],
    "DSBX_PollResp": [
        ("bool", "ok"),
        ("int", "now_ms"),
        ("ref array<ref DSBX_Order>", "ops"),
    ],
    "DSBX_AckResp": [
        ("bool", "ok"),
    ],
}

FORBIDDEN_TOKENS = (
    ".Replace(",
    "JsonLoadFile",
    "GET_now",
    "POST_now",
    "EnableDebug",
    "GetGame().GetTime(",
    ".GetTime(",
    "CallLater(",
    "WriteToString(",
)


def _strip_comments(text: str) -> str:
    """Elimina comentarios // y /* */ conservando literales de cadena y saltos de linea."""
    out = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                if text[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _extract_block(text: str, open_brace_idx: int) -> str:
    """Devuelve el contenido entre '{' en open_brace_idx y su '}' correspondiente."""
    depth = 0
    in_str = False
    i = open_brace_idx
    n = len(text)
    while i < n:
        ch = text[i]
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
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_idx + 1 : i]
        i += 1
    return ""


def _find_call_args(code: str, func_name: str) -> list[list[str]]:
    """Extrae la lista de argumentos de cada llamada a func_name(...) (excluyendo su declaracion)."""
    calls = []
    for m in re.finditer(rf"(?<![\w.])(?!(?:int|void|bool|float|string)\s+){re.escape(func_name)}\s*\(", code):
        prefix = code[max(0, m.start() - 16) : m.start()]
        if re.search(r"\b(?:int|void|bool|float|string)\s+$", prefix):
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


def _find_method_body(code: str, method_name: str) -> str:
    pattern = re.compile(
        rf"\b(?:static\s+|override\s+)*(?:void|bool|int|float|string|DSBX_\w+)\s+{re.escape(method_name)}\s*\([^)]*\)\s*\{{",
        re.MULTILINE,
    )
    m = pattern.search(code)
    if not m:
        return ""
    brace_idx = code.find("{", m.start())
    return _extract_block(code, brace_idx)


def _find_class_body(code: str, class_name: str) -> str:
    pattern = re.compile(rf"\bclass\s+{re.escape(class_name)}\b[^{{]*\{{", re.MULTILINE)
    m = pattern.search(code)
    if not m:
        return ""
    brace_idx = code.find("{", m.start())
    return _extract_block(code, brace_idx)


def _read_stripped_c_files(mod_dir: Path) -> dict[str, str]:
    result = {}
    for rel in EXPECTED_C_FILES:
        p = mod_dir / rel
        if p.is_file():
            raw = p.read_bytes().decode("utf-8", errors="replace")
            result[rel] = _strip_comments(raw)
    return result


def check_m1_forma(mod_dir: Path) -> list[str]:
    violations = []
    if not mod_dir.is_dir():
        return [f"M1: no existe el directorio {mod_dir}"]
    actual_files = sorted(
        p.relative_to(mod_dir).as_posix() for p in mod_dir.rglob("*") if p.is_file()
    )
    expected_files = sorted(EXPECTED_REL_FILES)
    if actual_files != expected_files:
        violations.append(f"M1: arbol de ficheros distinto: actual={actual_files} esperado={expected_files}")

    pbo_prefix = mod_dir / "$PBOPREFIX$"
    if pbo_prefix.is_file():
        txt = pbo_prefix.read_bytes().decode("utf-8", errors="replace").strip()
        if txt != "DayZSandbox":
            violations.append(f"M1: $PBOPREFIX$ debe ser 'DayZSandbox', es '{txt}'")

    inc_lst = mod_dir / "include.lst"
    if inc_lst.is_file():
        txt = inc_lst.read_bytes().decode("utf-8", errors="replace").strip()
        if txt != "*.c":
            violations.append(f"M1: include.lst debe ser '*.c', es '{txt}'")

    cfg_path = mod_dir / "config.cpp"
    if cfg_path.is_file():
        cfg = _strip_comments(cfg_path.read_bytes().decode("utf-8", errors="replace"))
        if not re.search(r'requiredAddons\s*\[\s*\]\s*=\s*\{\s*"DZ_Data"\s*\}\s*;', cfg):
            violations.append("M1: config.cpp debe declarar requiredAddons[] = {\"DZ_Data\"};")
        if not re.search(r'dependencies\s*\[\s*\]\s*=\s*\{\s*"Game"\s*,\s*"Mission"\s*\}\s*;', cfg):
            violations.append("M1: config.cpp debe declarar dependencies[] = {\"Game\", \"Mission\"};")
        defs_body = _find_class_body(cfg, "defs")
        if not defs_body:
            violations.append("M1: config.cpp no tiene class defs")
        else:
            subclasses = re.findall(r"\bclass\s+(\w+)\b", defs_body)
            if sorted(subclasses) != ["gameScriptModule", "missionScriptModule"]:
                violations.append(f"M1: defs debe tener exactamente gameScriptModule y missionScriptModule, tiene {subclasses}")
            if '"DayZSandbox/scripts/3_Game"' not in defs_body:
                violations.append("M1: falta ruta DayZSandbox/scripts/3_Game en gameScriptModule")
            if '"DayZSandbox/scripts/5_Mission"' not in defs_body:
                violations.append("M1: falta ruta DayZSandbox/scripts/5_Mission en missionScriptModule")
            if "4_World" in defs_body or "worldScriptModule" in defs_body:
                violations.append("M1: 4_World no debe estar en defs en F1b")

    c_files = _read_stripped_c_files(mod_dir)
    for rel, code in c_files.items():
        for m in re.finditer(r"\bmodded\s+class\s+(\w+)([^\n{]*)\{", code):
            tail = m.group(2).strip()
            if ":" in tail or "extends" in tail:
                violations.append(f"M1: {rel}: modded class {m.group(1)} no debe llevar herencia")
    return violations


def check_m2_tokens_prohibidos(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    for rel, code in c_files.items():
        for tok in FORBIDDEN_TOKENS:
            if tok in code:
                violations.append(f"M2: {rel} contiene token prohibido '{tok}'")
    for rel, code in _read_stripped_c_files(mod_dir).items():
        for bad in re.finditer(r"(?<!ERestResultState\.)\bEREST_[A-Z_]+|(?<!ERestOption\.)\bERESTOPTION_[A-Z_]+", code):
            violations.append(f"M2: miembro de enum sin calificar en {rel}: {bad.group(0)}")
    return violations


def check_m3_fifo(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    for rel, code in c_files.items():
        if re.search(r"\bm_Order\s*\.\s*Remove\s*\(", code):
            violations.append(f"M3: {rel} usa m_Order.Remove( en lugar de m_Order.RemoveOrdered(")
    cache_code = c_files.get("scripts/3_Game/DSBX_Cache.c", "")
    evict_body = _find_method_body(cache_code, "EvictOneExpired")
    if not evict_body:
        violations.append("M3: falta EvictOneExpired en DSBX_Cache.c")
    else:
        if "m_Order.RemoveOrdered(" not in evict_body:
            violations.append("M3: EvictOneExpired debe expulsar con m_Order.RemoveOrdered(")
        if "m_RetencionHasta <= now" not in evict_body:
            violations.append("M3: EvictOneExpired debe comprobar m_RetencionHasta <= now")
    return violations


def _log_call_args(code: str) -> list[str]:
    """Argumentos de cada llamada a Log(...) (sin la definicion de Log), con parentesis equilibrados."""
    out = []
    for m in re.finditer(r"\bLog\s*\(", code):
        if re.search(r"\bvoid\s+$", code[max(0, m.start() - 12):m.start()]):
            continue
        depth, j = 1, m.end()
        while j < len(code) and depth:
            if code[j] == "(":
                depth += 1
            elif code[j] == ")":
                depth -= 1
            j += 1
        out.append(code[m.end():j - 1])
    return out


def check_m4_clave(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    if not peer_code:
        return ["M4: falta DSBX_Peer.c"]

    for rel, code in c_files.items():
        if rel != "scripts/3_Game/DSBX_Peer.c" and re.search(r"\bm_Key\b", code):
            violations.append(f"M4: m_Key aparece fuera de DSBX_Peer.c en {rel}")

    # Ningun Log lleva la clave, la consulta con la clave ni la ruta (P-09, §3.12)
    for rel, code in c_files.items():
        for arg in _log_call_args(code):
            if re.search(r"\bm_Key\b|\bKeyQuery\b|\.\s*key\b|\bruta\b", arg):
                violations.append(f"M4: un Log lleva la clave o la ruta en {rel}: Log({arg.strip()[:60]})")

    load_body = _find_method_body(peer_code, "LoadConfig")
    key_query_body = _find_method_body(peer_code, "KeyQuery")
    send_body = _find_method_body(peer_code, "Send")
    log_body = _find_method_body(peer_code, "Log")

    if not load_body:
        violations.append("M4: falta LoadConfig en DSBX_Peer.c")
    if not key_query_body:
        violations.append("M4: falta KeyQuery en DSBX_Peer.c")
    if not send_body:
        violations.append("M4: falta Send en DSBX_Peer.c")
    if not log_body:
        violations.append("M4: falta Log en DSBX_Peer.c")

    # m_Key solo en su declaracion, en LoadConfig y en KeyQuery
    total_m_key = len(re.findall(r"\bm_Key\b", peer_code))
    decl_m_key = len(re.findall(r"\bstring\s+m_Key\s*;", peer_code))
    load_m_key = len(re.findall(r"\bm_Key\b", load_body))
    kq_m_key = len(re.findall(r"\bm_Key\b", key_query_body))
    if decl_m_key != 1 or load_m_key != 1 or kq_m_key != 1 or total_m_key != 3:
        violations.append(
            f"M4: m_Key debe aparecer exactamente 1 vez en declaracion, 1 en LoadConfig y 1 en KeyQuery "
            f"(decl={decl_m_key}, load={load_m_key}, kq={kq_m_key}, total={total_m_key})"
        )
    if not re.search(r"\bm_Key\s*=\s*cfg\.key\s*;", load_body):
        violations.append("M4: LoadConfig debe asignar m_Key = cfg.key;")
    for m in re.finditer(r"(\w+)\s*=\s*cfg\.key\b", peer_code):
        if m.group(1) != "m_Key":
            violations.append(f"M4: alias de cfg.key en '{m.group(1)}'")

    # LoadConfig comprueba el alfabeto de §3.1 con KeyUsable(cfg.key)
    if not re.search(r"!\s*KeyUsable\s*\(\s*cfg\.key\s*\)", load_body):
        violations.append("M4: LoadConfig debe validar el alfabeto de cfg.key con !KeyUsable(cfg.key)")
    key_usable_body = _find_method_body(peer_code, "KeyUsable")
    is_key_char_body = _find_method_body(peer_code, "IsKeyChar")
    if not key_usable_body or "16" not in key_usable_body or "128" not in key_usable_body or "IsKeyChar" not in key_usable_body:
        violations.append("M4: KeyUsable debe comprobar longitud 16..128 e IsKeyChar")
    if not is_key_char_body or "95" not in is_key_char_body or "45" not in is_key_char_body:
        violations.append("M4: IsKeyChar debe comprobar el alfabeto [A-Za-z0-9_-]")

    # DSBX_PeerConfig solo en su definicion y en LoadConfig
    for rel, code in c_files.items():
        if rel == "scripts/3_Game/DSBX_Messages.c":
            cnt = len(re.findall(r"\bDSBX_PeerConfig\b", code))
            if cnt != 1:
                violations.append(f"M4: DSBX_PeerConfig en DSBX_Messages.c debe aparecer 1 vez, aparece {cnt}")
        elif rel == "scripts/3_Game/DSBX_Peer.c":
            total_cfg_cls = len(re.findall(r"\bDSBX_PeerConfig\b", code))
            in_load = len(re.findall(r"\bDSBX_PeerConfig\b", load_body))
            if total_cfg_cls != in_load or in_load < 1:
                violations.append("M4: DSBX_PeerConfig en DSBX_Peer.c solo puede aparecer dentro de LoadConfig")
        else:
            if re.search(r"\bDSBX_PeerConfig\b", code):
                violations.append(f"M4: DSBX_PeerConfig aparece en {rel}")

    # KeyQuery() solo dentro del argumento de ruta (2o argumento) de Send(...)
    for rel, code in c_files.items():
        if rel != "scripts/3_Game/DSBX_Peer.c" and re.search(r"\bKeyQuery\b", code):
            violations.append(f"M4: KeyQuery aparece fuera de DSBX_Peer.c en {rel}")
    total_kq = len(re.findall(r"\bKeyQuery\s*\(\s*\)", peer_code))
    send_calls = [args for args in _find_call_args(peer_code, "Send") if len(args) == 3]
    kq_in_send_route = sum(len(re.findall(r"\bKeyQuery\s*\(\s*\)", args[1])) for args in send_calls)
    kq_in_send_body = sum(len(re.findall(r"\bKeyQuery\s*\(\s*\)", args[2])) for args in send_calls)
    if kq_in_send_body > 0:
        violations.append("M4: KeyQuery() no puede aparecer en el argumento body de Send")
    # 1 aparicion es la firma `string KeyQuery()`, el resto deben estar en el 2o argumento de Send
    if total_kq != 1 + kq_in_send_route or kq_in_send_route < 1:
        violations.append(
            f"M4: KeyQuery() solo puede aparecer en su definicion y en el argumento ruta de Send "
            f"(total={total_kq}, en_ruta={kq_in_send_route})"
        )

    # Dentro de Send, ruta solo en la firma y como argumento de .GET( y .POST(;
    # body, ademas, en la comparacion con DSBX_WIRE_CAP (P-09)
    if send_body:
        ruta_uses = len(re.findall(r"\bruta\b", send_body))
        ruta_get = len(re.findall(r"\.\s*GET\s*\(\s*\w+\s*,\s*ruta\s*\)", send_body))
        ruta_post = len(re.findall(r"\.\s*POST\s*\(\s*\w+\s*,\s*ruta\s*,\s*body\s*\)", send_body))
        if ruta_uses != ruta_get + ruta_post:
            violations.append(
                f"M4: dentro de Send, 'ruta' solo puede usarse en .GET(cb, ruta) y .POST(cb, ruta, body) "
                f"(usos={ruta_uses}, permitidos={ruta_get + ruta_post})"
            )
        body_uses = len(re.findall(r"\bbody\b", send_body))
        body_cap = len(re.findall(r"\bbody\.Length\s*\(\s*\)\s*[<>!=]+\s*DSBX_WIRE_CAP\b", send_body))
        body_post = len(re.findall(r"\.\s*POST\s*\(\s*\w+\s*,\s*ruta\s*,\s*body\s*\)", send_body))
        if body_uses != body_cap + body_post:
            violations.append(
                f"M4: dentro de Send, 'body' solo puede usarse en la comparacion con DSBX_WIRE_CAP y en .POST "
                f"(usos={body_uses}, permitidos={body_cap + body_post})"
            )

    # Un unico Log() y Print/Error/Debug. solo dentro de Log
    all_log_defs = 0
    for rel, code in c_files.items():
        all_log_defs += len(re.findall(r"\bvoid\s+Log\s*\(", code))
        for tok in (r"\bPrint\s*\(", r"\bError\s*\(", r"\bDebug\s*\."):
            matches = len(re.findall(tok, code))
            if rel == "scripts/3_Game/DSBX_Peer.c" and tok == r"\bPrint\s*\(":
                in_log = len(re.findall(tok, log_body))
                if matches != in_log or in_log != 1:
                    violations.append(f"M4: Print( solo puede aparecer dentro de Log (total={matches}, en_Log={in_log})")
            elif matches > 0:
                violations.append(f"M4: {rel} contiene '{tok}' fuera de Log")
    if all_log_defs != 1:
        violations.append(f"M4: debe existir exactamente una definicion de Log(), hay {all_log_defs}")
    return violations


def check_m5_wire_cap_y_send(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    cap_defs = []
    for rel, code in c_files.items():
        for m in re.finditer(r"\bconst\s+int\s+DSBX_WIRE_CAP\s*=\s*(\d+)\s*;", code):
            cap_defs.append((rel, int(m.group(1))))
    if len(cap_defs) != 1:
        violations.append(f"M5: const int DSBX_WIRE_CAP debe definirse exactamente una vez, encontrado: {cap_defs}")
    elif cap_defs[0][1] != WIRE_CAP:
        violations.append(f"M5: DSBX_WIRE_CAP={cap_defs[0][1]} no coincide con bridge.WIRE_CAP={WIRE_CAP}")

    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    send_body = _find_method_body(peer_code, "Send")
    if not send_body:
        violations.append("M5: falta Send en DSBX_Peer.c")
    else:
        if "body.Length() > DSBX_WIRE_CAP" not in send_body:
            violations.append("M5: Send debe contener literalmente 'body.Length() > DSBX_WIRE_CAP'")
        m_cap = re.search(r"if\s*\(\s*body\.Length\(\)\s*>\s*DSBX_WIRE_CAP\s*\)\s*\{([^}]*)\}", send_body)
        if not m_cap or "return" not in m_cap.group(1):
            violations.append("M5: la rama body.Length() > DSBX_WIRE_CAP en Send debe cortar el envio con return")

    for rel, code in c_files.items():
        for m in re.finditer(r"\.\s*(?:GET|POST)\s*\(", code):
            if rel != "scripts/3_Game/DSBX_Peer.c":
                violations.append(f"M5: {rel} llama a {m.group(0)} fuera de Send")
        if rel == "scripts/3_Game/DSBX_Peer.c":
            total_http = len(re.findall(r"\.\s*(?:GET|POST)\s*\(", code))
            in_send = len(re.findall(r"\.\s*(?:GET|POST)\s*\(", send_body))
            if total_http != in_send or in_send != 2:
                violations.append(f"M5: .GET( y .POST( solo pueden estar dentro de Send (total={total_http}, en_Send={in_send})")

    all_code = "\n".join(c_files.values())
    if '"result_too_large"' not in all_code:
        violations.append('M5: falta el sustituto "result_too_large"')
    return violations


REQUIRED_GUARDS = {
    "ValidHello": ["!resp", "!resp.ok", "!IsHex(resp.session,16)", "resp.conn<1", "resp.lease_ms<=0",
                   "resp.hold_ms<=0", "resp.wire_cap<1024"],
    "ValidOrder": ["!order", 'order.op_id==""', "!IsHex(order.session,16)", "order.conn<0",
                   "!IsHex(order.epoch,32)", "!IsHex(order.inst,32)", 'order.verb==""',
                   "order.issued_ms<0", "order.ttl_ms<=0"],
    "ValidPoll": ["!resp", "!resp.ok", "resp.now_ms<0", "!resp.ops", "resp.ops.Count()>1",
                  "resp.ops.Count()==1&&!ValidOrder(resp.ops.Get(0))"],
    "ValidAck": ["!resp", "!resp.ok"],
}


def check_m6_validadores(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    msg_code = c_files.get("scripts/3_Game/DSBX_Messages.c", "")
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")

    vh = _find_method_body(msg_code, "ValidHello")
    vo = _find_method_body(msg_code, "ValidOrder")
    vp = _find_method_body(msg_code, "ValidPoll")
    va = _find_method_body(msg_code, "ValidAck")

    # Cada guarda de §3.5 tal cual, con su salida: if (<condicion>) { return false; }
    for vname, vbody in (("ValidHello", vh), ("ValidOrder", vo), ("ValidPoll", vp), ("ValidAck", va)):
        if not vbody:
            continue
        have = {re.sub(r"\s+", "", c) for c in re.findall(r"if\s*\((.*?)\)\s*\{\s*return\s+false\s*;\s*\}", vbody, re.S)}
        for need in REQUIRED_GUARDS[vname]:
            if need not in have:
                violations.append(f"M6: {vname} no tiene la guarda if ({need}) {{ return false; }}")
        if len(re.findall(r"\breturn\s+true\s*;", vbody)) != 1 \
                or not re.search(r"\breturn\s+true\s*;\s*\}?\s*$", vbody.strip()):
            violations.append(f"M6: {vname} debe tener un solo return true, al final")

    if not vh:
        violations.append("M6: falta ValidHello")
    else:
        for req in ("resp.ok", "IsHex(resp.session, 16)", "resp.conn", "resp.lease_ms", "resp.hold_ms", "resp.wire_cap"):
            if req not in vh:
                violations.append(f"M6: ValidHello no comprueba '{req}'")

    if not vo:
        violations.append("M6: falta ValidOrder")
    else:
        for req in (
            "order.op_id",
            "IsHex(order.session, 16)",
            "order.conn",
            "IsHex(order.epoch, 32)",
            "IsHex(order.inst, 32)",
            "order.verb",
            "order.issued_ms",
            "order.ttl_ms",
        ):
            if req not in vo:
                violations.append(f"M6: ValidOrder no comprueba '{req}'")
        # Revision Enforce (15-nov, H-08): args lo decide el verbo (bad_args); una sola conducta
        if re.search(r"\border\s*\.\s*args\b", vo):
            violations.append("M6: ValidOrder no debe mirar order.args: lo decide el verbo (bad_args)")

    if not vp:
        violations.append("M6: falta ValidPoll")
    else:
        for req in ("resp.ok", "resp.now_ms", "resp.ops", "ValidOrder("):
            if req not in vp:
                violations.append(f"M6: ValidPoll no comprueba '{req}'")

    if not va:
        violations.append("M6: falta ValidAck")
    else:
        if "resp.ok" not in va:
            violations.append("M6: ValidAck no comprueba 'resp.ok'")

    for call_name in ("ValidHello(", "ValidPoll(", "ValidAck("):
        if call_name not in peer_code:
            violations.append(f"M6: DSBX_Peer.c no invoca {call_name}")

    # Los miembros de ms y conn de las clases de lectura deben ser int, nunca float
    int_fields = {
        "DSBX_HelloResp": ("conn", "lease_ms", "hold_ms", "wire_cap"),
        "DSBX_Order": ("conn", "issued_ms", "ttl_ms"),
        "DSBX_PollResp": ("now_ms",),
    }
    for cls_name, fields in int_fields.items():
        cls_body = _find_class_body(msg_code, cls_name)
        for fname in fields:
            if not re.search(rf"\bint\s+{re.escape(fname)}\s*;", cls_body):
                violations.append(f"M6: {cls_name}.{fname} debe ser de tipo int")
    return violations


def check_m7_guarda_efectos(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    literal_guard = "if (!EffectGuard(order)) { GuardFailed(order); return; }"

    for step_fn in ("StepRetirar", "StepAnotar"):
        body = _find_method_body(peer_code, step_fn)
        if not body:
            violations.append(f"M7: falta {step_fn} en DSBX_Peer.c")
            continue
        stripped = body.strip()
        if not stripped.startswith(literal_guard):
            violations.append(f"M7: la primera sentencia de {step_fn} debe ser exactamente '{literal_guard}'")
        after_guard = stripped[len(literal_guard) :]
        if "SetGeneration(" not in after_guard:
            violations.append(f"M7: {step_fn} debe llamar a SetGeneration( despues de la guarda")

    # Revision Enforce (15-nov): tras un hello nuevo, una orden de otra sesion o presentacion no surte efecto
    eg_body = re.sub(r"\s+", " ", _find_method_body(peer_code, "EffectGuard"))
    if not eg_body:
        violations.append("M7: falta EffectGuard en DSBX_Peer.c")
    for cond, reason in (("order.session != m_Session", "stale_session"), ("order.conn != m_Conn", "stale_conn")):
        want = f'if ({cond}) {{ m_GuardFailReason = "{reason}"; return false; }}'
        if eg_body and want not in eg_body:
            violations.append(f"M7: EffectGuard debe cortar con '{want}'")

    for rel, code in c_files.items():
        if rel == "scripts/3_Game/DSBX_World.c":
            total_sg = len(re.findall(r"\bSetGeneration\s*\(", code))
            def_sg = len(re.findall(r"\bvoid\s+SetGeneration\s*\(", code))
            if total_sg != def_sg:
                violations.append("M7: DSBX_World.c no debe invocar SetGeneration(")
        elif rel == "scripts/3_Game/DSBX_Peer.c":
            total_sg = len(re.findall(r"\bSetGeneration\s*\(", code))
            in_ret = len(re.findall(r"\bSetGeneration\s*\(", _find_method_body(code, "StepRetirar")))
            in_ano = len(re.findall(r"\bSetGeneration\s*\(", _find_method_body(code, "StepAnotar")))
            if total_sg != in_ret + in_ano or in_ret != 1 or in_ano != 1:
                violations.append("M7: SetGeneration( solo puede llamarse una vez en StepRetirar y una en StepAnotar")
        else:
            if re.search(r"\bSetGeneration\s*\(", code):
                violations.append(f"M7: SetGeneration( aparece fuera de lugar en {rel}")
    return violations


def check_m8_dedup_primero(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    body = _find_method_body(peer_code, "HandleOrder")
    if not body:
        return ["M8: falta HandleOrder en DSBX_Peer.c"]

    if not re.search(r"\bint\s+restante\s*=\s*order\.ttl_ms\s*-\s*\(\s*\w+\s*-\s*order\.issued_ms\s*\)\s*;", body):
        violations.append("M8: HandleOrder debe calcular restante en int")

    cache_pos = body.find("m_Cache.GetLive(")
    if cache_pos < 0:
        violations.append("M8: HandleOrder no consulta m_Cache.GetLive(")
        return violations

    dup_pos = body.find("m_SendDup = true")
    if dup_pos < 0:
        violations.append("M8: HandleOrder no marca m_SendDup = true para entradas terminadas")

    for check_tok in (
        '"stale_session"',
        '"stale_inst"',
        '"stale_conn"',
        '"stale_epoch"',
        '"expired"',
        "now > plazoLocal",
        "order.session != m_Session",
        "order.inst != m_Inst",
        "order.conn != m_Conn",
        "order.epoch != m_Epoch",
    ):
        pos = body.find(check_tok)
        if pos < 0:
            violations.append(f"M8: falta comprobacion '{check_tok}' en HandleOrder")
        elif pos < cache_pos or (dup_pos >= 0 and pos < dup_pos):
            violations.append(f"M8: '{check_tok}' va antes de la consulta/dedup de la cache en HandleOrder")
    return violations


def _has_wire_key(body: str, key: str) -> bool:
    """La clave aparece tal cual o dentro de un literal Enforce, con las comillas escapadas."""
    return key in body or key in body.replace('\\"', '"')


def check_m9_contrato_cable(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    wire_code = c_files.get("scripts/3_Game/DSBX_Wire.c", "")
    msg_code = c_files.get("scripts/3_Game/DSBX_Messages.c", "")
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    all_code = "\n".join(c_files.values())

    # Clases de lectura y sus miembros (nombres; el tipo int de ms lo comprueba M6)
    for cls_name, members in EXPECTED_JSON_CLASSES.items():
        cls_body = _find_class_body(msg_code, cls_name)
        if not cls_body:
            violations.append(f"M9: falta clase {cls_name} en DSBX_Messages.c")
            continue
        for _, field_name in members:
            if not re.search(rf"\b{re.escape(field_name)}\s*;", cls_body):
                violations.append(f"M9: falta miembro {field_name} en {cls_name}")

    # WireText: un solo parametro, sin recortar
    m_wt = re.search(r"\bstring\s+WireText\s*\(([^)]*)\)", wire_code)
    if not m_wt:
        violations.append("M9: falta WireText en DSBX_Wire.c")
    else:
        params = [p.strip() for p in m_wt.group(1).split(",") if p.strip()]
        if len(params) != 1:
            violations.append(f"M9: WireText debe tener exactamente 1 parametro, tiene {params}")

    wt_body = _find_method_body(wire_code, "WireText")
    if wt_body:
        n_mods = re.findall(r"\bn\s*[-+*/%]?=(?!=)|\bn\s*(?:\+\+|--)|(?:\+\+|--)\s*n\b", wt_body)
        if "int n = s.Length();" not in wt_body or len(n_mods) != 1:
            violations.append("M9: WireText debe recorrer la cadena entera: int n = s.Length(); y n no se toca")
        i_mods = re.findall(r"\bi\s*[-+*/%]?=(?!=)|\bi\s*(?:\+\+|--)|(?:\+\+|--)\s*i\b", wt_body)
        if "int i = 0;" not in wt_body or "i = i + 1;" not in wt_body or len(i_mods) != 2:
            violations.append("M9: WireText debe empezar en i = 0 y avanzar de uno en uno (i = i + 1)")
        m_wl = re.search(r"while\s*\(\s*i\s*<\s*n\s*\)\s*\{", wt_body)
        if not m_wl:
            violations.append("M9: WireText debe recorrer con while (i < n)")
        elif re.search(r"\b(?:break|return)\b", _extract_block(wt_body, wt_body.find("{", m_wl.start()))):
            violations.append("M9: el bucle de WireText no puede cortar (break/return): nada se recorta")
        subs = re.findall(r"\.\s*Substring\s*\([^)]*\)", wt_body)
        if re.search(r"\bs\s*=(?!=)", wt_body) or any(re.sub(r"\s+", "", x) != ".Substring(i,1)" for x in subs):
            violations.append("M9: WireText no puede reasignar ni cortar la cadena de entrada")

    if "hello_modset_truncated" in all_code:
        violations.append("M9: hello_modset_truncated no debe aparecer")
    if '"hello_too_large bytes="' not in peer_code:
        violations.append("M9: falta log hello_too_large en DSBX_Peer.c")

    # El modset nunca se recorta
    for modset_var in ("modset", "m_Modset"):
        if re.search(rf"\b{modset_var}\s*\.\s*(?:Remove|RemoveOrdered|Resize|Clear)\s*\(", all_code):
            violations.append(f"M9: no se deben quitar elementos de {modset_var}")

    hello_body = _find_method_body(wire_code, "HelloBody")
    read_body = _find_method_body(wire_code, "WorldReadJson")
    res_body = _find_method_body(wire_code, "ResultBody")
    cat_body = _find_method_body(wire_code, "CatalogPageBody")

    for key in ('"proto"', '"dsbx1"', '"peer"', '"inst"', '"epoch"', '"mod_ver"', '"build"', '"map"', '"world_size"', '"modset"', '"actor_engine"', '"none"'):
        if not _has_wire_key(hello_body, key):
            violations.append(f"M9: falta {key} en HelloBody")
    m_loop = re.search(r"while\s*\(\s*i\s*<\s*modset\.Count\(\)\s*\)\s*\{", hello_body)
    if not m_loop:
        violations.append("M9: HelloBody debe recorrer el modset entero con while (i < modset.Count())")
    else:
        loop_block = _extract_block(hello_body, hello_body.find("{", m_loop.start()))
        if re.search(r"\b(?:break|return)\b", loop_block):
            violations.append("M9: el bucle del modset de HelloBody no puede cortar (break/return): nada se recorta")
    if '",\\"map\\":" + WireText(mapName)' not in hello_body:
        violations.append("M9: map debe escribirse con WireText(mapName) en HelloBody")
    if "WireText(modVer)" not in hello_body or "WireText(build)" not in hello_body or "WireText(modset.Get(" not in hello_body:
        violations.append("M9: mod_ver, build y los nombres del modset deben pasar por WireText en HelloBody")
    if "WireId(role)" not in hello_body or "WireId(inst)" not in hello_body or "WireId(epoch)" not in hello_body:
        violations.append("M9: role, inst y epoch deben pasar por WireId en HelloBody")

    for key in ('"epoch"', '",\\"generation\\":"', '"registry_n"', '"registry_sha256"', '"session"', '"op_id"', '"rev"', '"hash"', '"null"'):
        if not _has_wire_key(read_body, key):
            violations.append(f"M9: falta {key} en WorldReadJson")
    if "WireId(world.GetEpoch())" not in read_body or "WireId(gen.session)" not in read_body or "WireId(gen.op_id)" not in read_body or "WireId(gen.hash)" not in read_body:
        violations.append("M9: los identificadores de WorldReadJson deben pasar por WireId")

    for key in ('"op_id"', '"session"', '"epoch"', '"status"', '"reason"', '"dup"', '"read"'):
        if not _has_wire_key(res_body, key):
            violations.append(f"M9: falta {key} en ResultBody")
    if "WireId(opId)" not in res_body or "WireId(session)" not in res_body or "WireId(epoch)" not in res_body or "WireId(status)" not in res_body:
        violations.append("M9: los identificadores de ResultBody deben pasar por WireId")

    for key in ('"catalog_id"', '"page"', '"pages"', '"build"', '"modset_hash"', '"classes"'):
        if not _has_wire_key(cat_body, key):
            violations.append(f"M9: falta {key} en CatalogPageBody")
    if "WireId(catalogId)" not in cat_body or "WireId(modsetHash)" not in cat_body or "WireText(build)" not in cat_body:
        violations.append("M9: catalog_id y modset_hash deben usar WireId y build debe usar WireText en CatalogPageBody")
    return violations


def check_m10_epoch(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    const_code = c_files.get("scripts/3_Game/DSBX_Const.c", "")
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    all_code = "\n".join(c_files.values())

    for const_name in ("DSBX_RPC_EPOCH", "DSBX_RPC_EPOCH_REQ"):
        m = re.search(rf"\bconst\s+int\s+{const_name}\s*=\s*(\d+)\s*;", const_code)
        if not m:
            violations.append(f"M10: falta {const_name} en DSBX_Const.c")
        elif int(m.group(1)) < 1_000_000:
            violations.append(f"M10: {const_name} debe ser >= 1000000")

    sin_cfg_body = _find_method_body(peer_code, "TickSinConfig")
    if not sin_cfg_body:
        violations.append("M10: falta TickSinConfig en DSBX_Peer.c")
    else:
        load_pos = sin_cfg_body.find("LoadConfig()")
        hello_pos = sin_cfg_body.find("ST_HELLO")
        guard_m = re.search(
            r"if\s*\(\s*m_IsClient\s*&&\s*m_Epoch\s*==\s*\"\"\s*\)\s*\{\s*return\s*;\s*\}",
            sin_cfg_body,
        )
        if not guard_m or load_pos < 0 or hello_pos < 0 or not (load_pos < guard_m.start() < hello_pos):
            violations.append("M10: TickSinConfig debe impedir pasar a ST_HELLO cuando m_IsClient && m_Epoch == \"\"")

    ins_cnt = len(re.findall(r"\bEvent_OnRPC\.Insert\s*\(", all_code))
    rem_cnt = len(re.findall(r"\bEvent_OnRPC\.Remove\s*\(", all_code))
    if ins_cnt != 1 or rem_cnt != 1:
        violations.append(f"M10: Event_OnRPC.Insert y .Remove deben aparecer 1 vez cada uno (insert={ins_cnt}, remove={rem_cnt})")
    return violations


def check_m11_errores(mod_dir: Path) -> list[str]:
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    all_code = "\n".join(c_files.values())

    p_err_body = _find_method_body(peer_code, "OnChannelPError")
    r_err_body = _find_method_body(peer_code, "OnChannelRError")
    lease_body = _find_method_body(peer_code, "CheckLeaseTimeout")

    if not p_err_body:
        violations.append("M11: falta OnChannelPError en DSBX_Peer.c")
    else:
        # Revision Enforce (15-nov, H-07): un 4xx llega con el estado 5, medido en juego; el simbolo
        # EREST_ERROR_CLIENTERROR vale 6 en el enum del script y casa un 500.
        m_ce = re.search(
            r"if\s*\(\s*!isTimeout\s*&&\s*errorCode\s*==\s*DSBX_Const\s*\.\s*REST_STATE_4XX\s*\)\s*\{",
            p_err_body,
        )
        if not m_ce:
            violations.append("M11: OnChannelPError debe comprobar errorCode == DSBX_Const.REST_STATE_4XX")
        else:
            brace_idx = p_err_body.find("{", m_ce.start())
            ce_block = _extract_block(p_err_body, brace_idx)
            if "m_State = DSBX_Const.ST_HELLO;" not in ce_block or 'm_Session = ""' not in ce_block or "m_Conn = 0" not in ce_block:
                violations.append("M11: un 4xx en P debe olvidar session/conn y volver a ST_HELLO")
            if "ComputeBackoffMs(m_ClientErrCountP)" not in ce_block:
                violations.append("M11: un 4xx en P debe aplicar espera creciente")

    const_code = c_files.get("scripts/3_Game/DSBX_Const.c", "")
    if not re.search(r"\bconst\s+int\s+REST_STATE_4XX\s*=\s*5\s*;", const_code):
        violations.append("M11: DSBX_Const.REST_STATE_4XX debe valer 5 (estado medido de un 4xx)")
    total_4xx = len(re.findall(r"\bREST_STATE_4XX\b", peer_code))
    in_p_4xx = len(re.findall(r"\bREST_STATE_4XX\b", p_err_body))
    if total_4xx != 1 or in_p_4xx != 1:
        violations.append(
            f"M11: REST_STATE_4XX solo puede usarse 1 vez en DSBX_Peer.c, dentro de OnChannelPError "
            f"(total={total_4xx}, en_P={in_p_4xx})"
        )
    if re.search(r"\bEREST_ERROR_CLIENTERROR\b", all_code):
        violations.append("M11: EREST_ERROR_CLIENTERROR no puede usarse: vale 6 y casa un 500 (H-07)")

    ctor = _find_method_body(peer_code, "DSBX_Peer")
    code_no_ctor = peer_code.replace(ctor, "", 1) if ctor else peer_code
    resets = [m.start() for m in re.finditer(r"\bm_ClientErrCountP\s*=\s*0\s*;", code_no_ctor)]
    valid_poll = code_no_ctor.find("ValidPoll(")
    if len(resets) != 1 or valid_poll < 0 or resets[0] < valid_poll:
        violations.append("M11: m_ClientErrCountP solo vuelve a 0 una vez, tras un poll valido (ValidPoll)")

    if not r_err_body:
        violations.append("M11: falta OnChannelRError en DSBX_Peer.c")
    else:
        if re.search(r"\b(?:REST_STATE_4XX|EREST_\w+|errorCode)\b", r_err_body):
            violations.append("M11: el canal R no debe mirar el codigo de error del motor (D1)")
        if "m_RMaxFailures" not in r_err_body or "RetryGapR(" not in r_err_body:
            violations.append("M11: OnChannelRError debe reintentar con RetryGapR y abandonar en m_RMaxFailures")
        # abandona al cuarto fallo: solo se compara con m_RMaxFailures, que vale R_MAX_FAILURES = 4 (D1)
        if len(re.findall(r">=\s*m_RMaxFailures\b", r_err_body)) < 2 \
                or re.search(r"(?:m_Attempts|m_CatFailures)\s*>=?\s*\d", r_err_body):
            violations.append("M11: OnChannelRError debe abandonar resultados y paginas solo con >= m_RMaxFailures")
    if not re.search(r"\bconst\s+int\s+R_MAX_FAILURES\s*=\s*4\s*;", const_code) \
            or not re.search(r"\bm_RMaxFailures\s*=\s*DSBX_Const\.R_MAX_FAILURES\s*;", peer_code):
        violations.append("M11: R_MAX_FAILURES debe valer 4 y asignarse a m_RMaxFailures")

    ok_body = _find_method_body(peer_code, "HandleChannelRSuccess")
    stale_re = re.compile(r"if\s*\(\s*m_CatSendSession\s*!=\s*m_CatSession\s*\)\s*\{\s*return\s*;\s*\}")
    stale_ok = True
    for body in (ok_body, r_err_body or ""):
        m_st = stale_re.search(body)
        first_mod = body.find("m_CatFailures =")
        if not m_st or first_mod < 0 or m_st.start() > first_mod:
            stale_ok = False
    if not stale_ok or "m_CatSendSession = m_CatSession;" not in peer_code:
        violations.append("M11: el acuse y el error de una pagina de otra sesion se descartan con return (m_CatSendSession)")

    if not lease_body:
        violations.append("M11: falta CheckLeaseTimeout en DSBX_Peer.c")
    else:
        if "(now - m_LastOkPollMs) > m_LeaseMs" not in lease_body or "m_State = DSBX_Const.ST_HELLO;" not in lease_body:
            violations.append("M11: CheckLeaseTimeout debe volver a ST_HELLO si pasa lease_ms sin poll valido")
    return violations


def check_m12_codificacion(mod_dir: Path) -> list[str]:
    violations = []
    for p in sorted(mod_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(mod_dir).as_posix()
        raw = p.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            violations.append(f"M12: {rel} tiene UTF-8 BOM")
        if b"\r" in raw:
            violations.append(f"M12: {rel} contiene CR (CRLF)")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            violations.append(f"M12: {rel} no es UTF-8 valido: {exc}")
    return violations


DIAG_ONLY_TOKENS = ("qa_step_gap_ms", "m_QaStepGapMs", "m_RetirarMs")


def check_m13_gancho_diag(mod_dir: Path) -> list[str]:
    """D-P3 del brief en partida: el gancho de G5 no existe fuera de #ifdef DIAG_DEVELOPER (texto crudo)."""
    violations = []
    seen = 0
    for rel in ("scripts/3_Game/DSBX_Messages.c", "scripts/3_Game/DSBX_Peer.c"):
        p = mod_dir / rel
        if not p.is_file():
            continue
        stack = []  # [kind, macro, es_diag_ahora]
        for n, line in enumerate(p.read_bytes().decode("utf-8", "replace").splitlines(), 1):
            s = line.strip()
            m = re.match(r"#\s*(ifdef|ifndef)\s+(\w+)", s)
            if m:
                stack.append([m.group(1), m.group(2), m.group(1) == "ifdef" and m.group(2) == "DIAG_DEVELOPER"])
                continue
            if re.match(r"#\s*else\b", s):
                if stack and stack[-1][1] == "DIAG_DEVELOPER":
                    stack[-1][2] = not stack[-1][2]
                elif stack:
                    stack[-1][2] = False
                continue
            if re.match(r"#\s*endif\b", s):
                if stack:
                    stack.pop()
                continue
            for tok in DIAG_ONLY_TOKENS:
                if re.search(r"\b%s\b" % tok, line):
                    seen += 1
                    if not any(e[2] for e in stack):
                        violations.append(f"M13: {tok} fuera de #ifdef DIAG_DEVELOPER en {rel}:{n}")
    if seen == 0:
        violations.append("M13: falta el gancho qa_step_gap_ms (D-P3)")
    return violations


def check_m14_peer_managed(mod_dir: Path) -> list[str]:
    """MUST de la revision Enforce (15-nov): el motor retiene cada RestCallback (BI T188795). Su m_Peer es
    debil y solo pasa a null al destruirse el peer si DSBX_Peer hereda de Managed."""
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    if not re.search(r"\bclass\s+DSBX_Peer\s*:\s*Managed\s*\{", peer_code):
        violations.append("M14: DSBX_Peer debe heredar de Managed (class DSBX_Peer : Managed)")
    cb_body = _find_class_body(peer_code, "DSBX_Callback")
    if not cb_body:
        violations.append("M14: falta la clase DSBX_Callback en DSBX_Peer.c")
    else:
        decls = re.findall(r"(?:\b(ref|autoptr)\s+)?\bDSBX_Peer\s+m_Peer\s*;", cb_body)
        if len(decls) != 1 or decls[0]:
            violations.append("M14: DSBX_Callback.m_Peer debe ser una referencia debil (sin ref ni autoptr)")
    return violations


def check_m15_cuarentena(mod_dir: Path) -> list[str]:
    """SHOULD de la revision Enforce (15-nov): con el backend caido, cada fallo creaba un callback nuevo y el
    presupuesto de 2000 se agotaba en ~67 min. Un callback cerrado por un fallo o por el vigilante pasa a
    cuarentena y se reutiliza pasado CALLBACK_QUARANTINE_MS, muy por encima del vigilante, para que una
    respuesta tardia de la peticion vieja no se tome por la nueva."""
    violations = []
    c_files = _read_stripped_c_files(mod_dir)
    peer_code = c_files.get("scripts/3_Game/DSBX_Peer.c", "")
    const_code = c_files.get("scripts/3_Game/DSBX_Const.c", "")

    m_q = re.search(r"\bconst\s+int\s+CALLBACK_QUARANTINE_MS\s*=\s*(\d+)\s*;", const_code)
    m_w = re.search(r"\bconst\s+int\s+WATCHDOG_MS\s*=\s*(\d+)\s*;", const_code)
    if not m_q or not m_w or int(m_q.group(1)) < 10 * int(m_w.group(1)):
        violations.append("M15: CALLBACK_QUARANTINE_MS debe existir y valer al menos 10 veces WATCHDOG_MS")
    # El tope dobla lo que acumula un periodo de cuarentena con el backend caido: P falla una vez por
    # DEFAULT_RETRY_MS, asi que caben 2 * CALLBACK_QUARANTINE_MS / DEFAULT_RETRY_MS.
    m_max = re.search(r"\bconst\s+int\s+CALLBACK_QUARANTINE_MAX\s*=\s*(\d+)\s*;", const_code)
    m_r = re.search(r"\bconst\s+int\s+DEFAULT_RETRY_MS\s*=\s*(\d+)\s*;", const_code)
    if not m_max or not m_q or not m_r \
            or int(m_max.group(1)) * int(m_r.group(1)) < 2 * int(m_q.group(1)):
        violations.append("M15: CALLBACK_QUARANTINE_MAX * DEFAULT_RETRY_MS debe ser >= 2 * CALLBACK_QUARANTINE_MS")

    def flat(name):
        return re.sub(r"\s+", " ", _find_method_body(peer_code, name))

    if "if (!success) { Quarantine(cb, canal); return; }" not in flat("SettleCallback"):
        violations.append("M15: SettleCallback debe mandar a cuarentena el callback de un fallo")

    acquire = flat("AcquireCallback")
    pop = acquire.find("pool.RemoveOrdered(last);")
    take = acquire.find("if (!cb) { cb = TakeFromQuarantine(canal); }")
    create = acquire.find("new DSBX_Callback(")
    if pop < 0 or take < 0 or create < 0 or not (pop < take < create):
        violations.append("M15: AcquireCallback debe probar el pool, luego la cuarentena y solo despues crear")

    # Sol, E-01..E-03: los tres ayudantes de la cuarentena, al pie de la letra (cada operacion en su sitio
    # y en su orden: insertar dentro del tope, el veto de CALLBACK_QUARANTINE_MS con su return, devolver el
    # extraido y desligar todos los callbacks desde el primero).
    pick = "array<ref DSBX_Callback> quarantine = m_QuarantineR; if (canal == DSBX_Const.CH_P) { quarantine = m_QuarantineP; }"
    exact = {
        "Quarantine": "cb.Retire(); cb.m_RetiredMs = NowMs(); " + pick
        + " if (quarantine.Count() < DSBX_Const.CALLBACK_QUARANTINE_MAX) { quarantine.Insert(cb); }",
        "TakeFromQuarantine": pick + " if (quarantine.Count() == 0) { return null; } DSBX_Callback oldest = quarantine.Get(0);"
        " if (!oldest || (NowMs() - oldest.m_RetiredMs) < DSBX_Const.CALLBACK_QUARANTINE_MS) { return null; }"
        " quarantine.RemoveOrdered(0); return oldest;",
        "DetachAll": "int k = 0; while (k < callbacks.Count()) { DSBX_Callback item = callbacks.Get(k);"
        " if (item) { item.Detach(); } k = k + 1; } callbacks.Clear();",
    }
    for name, want in exact.items():
        if flat(name).strip() != want:
            violations.append(f"M15: {name} debe ser exactamente: {want}")

    for wd, ch in (("WatchdogP", "CH_P"), ("WatchdogR", "CH_R")):
        body = flat(wd)
        if f"Quarantine(cb, DSBX_Const.{ch});" not in body or "cb.Retire();" in body:
            violations.append(f"M15: {wd} debe mandar el callback a cuarentena, no solo retirarlo")

    shutdown = flat("Shutdown")
    if "DetachAll(m_QuarantineP);" not in shutdown or "DetachAll(m_QuarantineR);" not in shutdown:
        violations.append("M15: Shutdown debe soltar el peer de los callbacks en cuarentena")
    return violations


ALL_CHECKS = {
    "M1": check_m1_forma,
    "M2": check_m2_tokens_prohibidos,
    "M3": check_m3_fifo,
    "M4": check_m4_clave,
    "M5": check_m5_wire_cap_y_send,
    "M6": check_m6_validadores,
    "M7": check_m7_guarda_efectos,
    "M8": check_m8_dedup_primero,
    "M9": check_m9_contrato_cable,
    "M10": check_m10_epoch,
    "M11": check_m11_errores,
    "M12": check_m12_codificacion,
    "M13": check_m13_gancho_diag,
    "M14": check_m14_peer_managed,
    "M15": check_m15_cuarentena,
}


class TestModStatic(unittest.TestCase):
    """Reglas estaticas M1-M15 sobre DayZSandbox/ y discriminacion X4 (a)-(z) y siguientes."""

    def test_m1_forma(self):
        self.assertEqual(check_m1_forma(REAL_MOD_DIR), [])

    def test_m2_tokens_prohibidos(self):
        self.assertEqual(check_m2_tokens_prohibidos(REAL_MOD_DIR), [])

    def test_m3_fifo(self):
        self.assertEqual(check_m3_fifo(REAL_MOD_DIR), [])

    def test_m4_clave(self):
        self.assertEqual(check_m4_clave(REAL_MOD_DIR), [])

    def test_m5_wire_cap_y_send(self):
        self.assertEqual(check_m5_wire_cap_y_send(REAL_MOD_DIR), [])

    def test_m6_validadores(self):
        self.assertEqual(check_m6_validadores(REAL_MOD_DIR), [])

    def test_m7_guarda_efectos(self):
        self.assertEqual(check_m7_guarda_efectos(REAL_MOD_DIR), [])

    def test_m8_dedup_primero(self):
        self.assertEqual(check_m8_dedup_primero(REAL_MOD_DIR), [])

    def test_m9_contrato_cable(self):
        self.assertEqual(check_m9_contrato_cable(REAL_MOD_DIR), [])

    def test_m10_epoch(self):
        self.assertEqual(check_m10_epoch(REAL_MOD_DIR), [])

    def test_m11_errores(self):
        self.assertEqual(check_m11_errores(REAL_MOD_DIR), [])

    def test_m12_codificacion(self):
        self.assertEqual(check_m12_codificacion(REAL_MOD_DIR), [])

    def test_m13_gancho_diag(self):
        self.assertEqual(check_m13_gancho_diag(REAL_MOD_DIR), [])

    def test_m14_peer_managed(self):
        self.assertEqual(check_m14_peer_managed(REAL_MOD_DIR), [])

    def test_m15_cuarentena(self):
        self.assertEqual(check_m15_cuarentena(REAL_MOD_DIR), [])

    def _assert_only_rule_fails(self, rel_file: str, old: str, new: str, expected_rule: str):
        with tempfile.TemporaryDirectory() as tmp:
            copy_dir = Path(tmp) / "DayZSandbox"
            shutil.copytree(REAL_MOD_DIR, copy_dir)
            target = copy_dir / rel_file
            content = target.read_bytes().decode("utf-8")
            self.assertEqual(content.count(old), 1, f"El fragmento a mutar no es unico en {rel_file}: {old[:60]!r}")
            mutated = content.replace(old, new, 1)
            target.write_bytes(mutated.encode("utf-8"))
            failed = [name for name, fn in ALL_CHECKS.items() if fn(copy_dir)]
            self.assertEqual(
                failed,
                [expected_rule],
                f"Mutacion en {rel_file} debia tumbar solo {expected_rule}, pero tumbo {failed}",
            )

    def _assert_only_rule_fails_multi(self, rel_file: str, pairs, expected_rule: str):
        with tempfile.TemporaryDirectory() as tmp:
            copy_dir = Path(tmp) / "DayZSandbox"
            shutil.copytree(REAL_MOD_DIR, copy_dir)
            target = copy_dir / rel_file
            content = target.read_bytes().decode("utf-8")
            for old, new in pairs:
                self.assertEqual(content.count(old), 1, f"El fragmento a mutar no es unico en {rel_file}: {old[:60]!r}")
                content = content.replace(old, new, 1)
            target.write_bytes(content.encode("utf-8"))
            failed = [name for name, fn in ALL_CHECKS.items() if fn(copy_dir)]
            self.assertEqual(failed, [expected_rule], f"Mutacion en {rel_file} debia tumbar solo {expected_rule}, pero tumbo {failed}")

    def test_x4_return_true_al_principio(self):
        # Sol r2 C-03: el unico return true se mueve al principio de ValidHello
        self._assert_only_rule_fails_multi(
            "scripts/3_Game/DSBX_Messages.c",
            [
                ("\t\tif (resp.wire_cap < 1024)\n\t\t{\n\t\t\treturn false;\n\t\t}\n\t\treturn true;\n",
                 "\t\tif (resp.wire_cap < 1024)\n\t\t{\n\t\t\treturn false;\n\t\t}\n"),
                ("static bool ValidHello(DSBX_HelloResp resp)\n\t{\n",
                 "static bool ValidHello(DSBX_HelloResp resp)\n\t{\n\t\treturn true;\n"),
            ],
            "M6",
        )

    def test_x4_mutations_a_to_z(self):
        cases = [
            # (a) M1: anadir 4_World a defs
            (
                "config.cpp",
                "class missionScriptModule",
                'class worldScriptModule { value = ""; files[] = {"DayZSandbox/scripts/4_World"}; }; class missionScriptModule',
                "M1",
            ),
            # (b) M2: un .Replace( en el UUID
            (
                "scripts/3_Game/DSBX_Wire.c",
                "string partA = raw.Substring(0, 8);",
                'raw.Replace("-", ""); string partA = raw.Substring(0, 8);',
                "M2",
            ),
            # (c) M3: Remove(i) en la expulsion
            (
                "scripts/3_Game/DSBX_Cache.c",
                "m_Order.RemoveOrdered(i);\n\t\t\t\tm_Entries.Remove(k);",
                "m_Order.Remove(i);\n\t\t\t\tm_Entries.Remove(k);",
                "M3",
            ),
            # (d) M4: un alias de la clave en otro miembro
            (
                "scripts/3_Game/DSBX_Peer.c",
                "m_Key = cfg.key;",
                "m_Key = cfg.key; m_Url = m_Key;",
                "M4",
            ),
            # (e) M4: KeyQuery() dentro del cuerpo de un envio
            (
                "scripts/3_Game/DSBX_Peer.c",
                'Send(DSBX_Const.CH_P, "hello?" + KeyQuery(), body);',
                'Send(DSBX_Const.CH_P, "hello?" + KeyQuery(), KeyQuery());',
                "M4",
            ),
            # (f) M4: quitar la comprobacion del alfabeto
            (
                "scripts/3_Game/DSBX_Peer.c",
                'else if (!KeyUsable(cfg.key))\n\t\t\t{\n\t\t\t\treason = "bad_key_chars";\n\t\t\t}',
                "",
                "M4",
            ),
            # (g) M5: DSBX_WIRE_CAP = 4000
            (
                "scripts/3_Game/DSBX_Const.c",
                "const int DSBX_WIRE_CAP = 3500;",
                "const int DSBX_WIRE_CAP = 4000;",
                "M5",
            ),
            # (h) M5: quitar la comparacion de Send
            (
                "scripts/3_Game/DSBX_Peer.c",
                "if (body.Length() > DSBX_WIRE_CAP)\n\t\t\t{\n\t\t\t\treturn -2;\n\t\t\t}",
                "",
                "M5",
            ),
            # (i) M5: invertirla (<=)
            (
                "scripts/3_Game/DSBX_Peer.c",
                "if (body.Length() > DSBX_WIRE_CAP)",
                "if (body.Length() <= DSBX_WIRE_CAP)",
                "M5",
            ),
            # (j) M5: un .POST( fuera de Send
            (
                "scripts/3_Game/DSBX_Peer.c",
                'int rc = Send(DSBX_Const.CH_P, "hello?" + KeyQuery(), body);',
                'm_Ctx.POST( null, "hello", body ); int rc = Send(DSBX_Const.CH_P, "hello?" + KeyQuery(), body);',
                "M5",
            ),
            # (k) M6: quitar la comprobacion de ok en ValidHello (ancla unica: la guarda que la sigue)
            (
                "scripts/3_Game/DSBX_Messages.c",
                "if (!resp.ok)\n\t\t{\n\t\t\treturn false;\n\t\t}\n\t\tif (!IsHex(resp.session, 16))",
                "if (!IsHex(resp.session, 16))",
                "M6",
            ),
            # (l) M6: float now_ms en DSBX_PollResp
            (
                "scripts/3_Game/DSBX_Messages.c",
                "int now_ms;",
                "float now_ms;",
                "M6",
            ),
            # (m) M7: quitar la guarda de StepAnotar
            (
                "scripts/3_Game/DSBX_Peer.c",
                "void StepAnotar(DSBX_Order order)\n\t{\n\t\tif (!EffectGuard(order)) { GuardFailed(order); return; }",
                "void StepAnotar(DSBX_Order order)\n\t{",
                "M7",
            ),
            # (n) M7: llamar a EffectGuard(order); sin usar su resultado
            (
                "scripts/3_Game/DSBX_Peer.c",
                "void StepAnotar(DSBX_Order order)\n\t{\n\t\tif (!EffectGuard(order)) { GuardFailed(order); return; }",
                "void StepAnotar(DSBX_Order order)\n\t{\n\t\tEffectGuard(order);",
                "M7",
            ),
            # (o) M7: invertir la condicion
            (
                "scripts/3_Game/DSBX_Peer.c",
                "void StepAnotar(DSBX_Order order)\n\t{\n\t\tif (!EffectGuard(order)) { GuardFailed(order); return; }",
                "void StepAnotar(DSBX_Order order)\n\t{\n\t\tif (EffectGuard(order)) { GuardFailed(order); return; }",
                "M7",
            ),
            # (p) M7: SetGeneration( antes de la guarda
            (
                "scripts/3_Game/DSBX_Peer.c",
                "void StepRetirar(DSBX_Order order)\n\t{\n\t\tif (!EffectGuard(order)) { GuardFailed(order); return; }\n\t\tm_ActiveEntry.m_StepsDone = 1;\n\t\tm_World.SetGeneration(null);",
                "void StepRetirar(DSBX_Order order)\n\t{\n\t\tm_World.SetGeneration(null);\n\t\tif (!EffectGuard(order)) { GuardFailed(order); return; }\n\t\tm_ActiveEntry.m_StepsDone = 1;",
                "M7",
            ),
            # (q) M8: mover la comprobacion de expired antes de la cache
            (
                "scripts/3_Game/DSBX_Peer.c",
                "DSBX_CacheEntry existing = m_Cache.GetLive(cacheKey, now);",
                'if (now > plazoLocal) { return; }\n\t\tDSBX_CacheEntry existing = m_Cache.GetLive(cacheKey, now);',
                "M8",
            ),
            # (r) M9: quitar "generation" del escritor del read
            (
                "scripts/3_Game/DSBX_Wire.c",
                'string body = "{\\"epoch\\":" + epochJson + ",\\"generation\\":" + genJson + ",\\"registry_n\\":" + world.GetRegistryN() + ",\\"registry_sha256\\":" + regShaJson + "}";',
                'string body = "{\\"epoch\\":" + epochJson + ",\\"registry_n\\":" + world.GetRegistryN() + ",\\"registry_sha256\\":" + regShaJson + "}";',
                "M9",
            ),
            # (s) M9: escribir map sin WireText
            (
                "scripts/3_Game/DSBX_Wire.c",
                'body = body + ",\\"map\\":" + WireText(mapName);',
                'body = body + ",\\"map\\":\\"" + mapName + "\\"";',
                "M9",
            ),
            # (t) M10: presentarse sin epoch
            (
                "scripts/3_Game/DSBX_Peer.c",
                'if (m_IsClient && m_Epoch == "")\n\t\t{\n\t\t\treturn;\n\t\t}\n\t\tm_State = DSBX_Const.ST_HELLO;',
                "m_State = DSBX_Const.ST_HELLO;",
                "M10",
            ),
            # (u) M11: tratar CLIENTERROR en P como un fallo cualquiera
            (
                "scripts/3_Game/DSBX_Peer.c",
                'if (m_State != DSBX_Const.ST_HELLO)\n\t\t\t{\n\t\t\t\tm_State = DSBX_Const.ST_HELLO;\n\t\t\t\tLog("state HELLO: client error on P");\n\t\t\t}',
                "",
                "M11",
            ),
            # (v) M11: quitar la vuelta a HELLO por lease vencido
            (
                "scripts/3_Game/DSBX_Peer.c",
                'm_State = DSBX_Const.ST_HELLO;\n\t\t\tLog("lease lost age_ms=" + ageMs + " tick_ms=" + TickMs());',
                'Log("lease lost age_ms=" + ageMs + " tick_ms=" + TickMs());',
                "M11",
            ),
            # (x) M11: en R, abandonar al primer CLIENTERROR, como la v1.1
            (
                "scripts/3_Game/DSBX_Peer.c",
                "void OnChannelRError(int kind, float now)\n\t{",
                "void OnChannelRError(int kind, float now)\n\t{\n\t\tif (ERestResultState.EREST_ERROR_CLIENTERROR == 0) { return; }",
                "M11",
            ),
            # (y) M4: un Log("send " + ruta); dentro de Send
            (
                "scripts/3_Game/DSBX_Peer.c",
                "if (!m_Ctx)\n\t\t{\n\t\t\treturn -1;\n\t\t}",
                'Log("send " + ruta);\n\t\tif (!m_Ctx)\n\t\t{\n\t\t\treturn -1;\n\t\t}',
                "M4",
            ),
            # (z) M9: volver a quitar nombres del modset hasta que el hello quepa
            (
                "scripts/3_Game/DSBX_Wire.c",
                "int i = 0;\n\t\t\t\twhile (i < modset.Count())",
                "if (modset.Count() > 16) { modset.RemoveOrdered(0); }\n\t\t\t\tint i = 0;\n\t\t\t\twhile (i < modset.Count())",
                "M9",
            ),
            # Del orquestador (X4 propio): un Log con la clave de la configuracion
            (
                "scripts/3_Game/DSBX_Peer.c",
                "m_Key = cfg.key;",
                'm_Key = cfg.key; Log("key " + cfg.key);',
                "M4",
            ),
            # Del orquestador: R abandona al primer fallo
            (
                "scripts/3_Game/DSBX_Peer.c",
                "if (m_SendingEntry.m_Attempts >= m_RMaxFailures)",
                "if (m_SendingEntry.m_Attempts >= 1)",
                "M11",
            ),
            # Del orquestador: el hello deja de anadir nombres del modset sin quitarlos del array
            (
                "scripts/3_Game/DSBX_Wire.c",
                "\t\t\t\twhile (i < modset.Count())\n\t\t\t\t{\n",
                "\t\t\t\twhile (i < modset.Count())\n\t\t\t\t{\n\t\t\t\t\tif (modsetItems.Length() > 2000) { break; }\n",
                "M9",
            ),
            # Del orquestador: un miembro de enum sin calificar
            (
                "scripts/3_Game/DSBX_Peer.c",
                "api.SetOption(ERestOption.ERESTOPTION_CONNECTION, 3);",
                "api.SetOption(ERESTOPTION_CONNECTION, 3);",
                "M2",
            ),
            # Del orquestador: el hello vuelve a poner a cero la cuenta de 4xx
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\t\tm_FailCountP = 0;\n\t\t\tm_HelloTooLargeLogged = false;\n",
                "\t\t\tm_FailCountP = 0;\n\t\t\tm_ClientErrCountP = 0;\n\t\t\tm_HelloTooLargeLogged = false;\n",
                "M11",
            ),
            # Sol C-02: WireText recorta en silencio
            (
                "scripts/3_Game/DSBX_Wire.c",
                "\t\tint n = s.Length();\n\t\tint i = 0;\n\t\twhile (i < n)\n\t\t{\n\t\t\tstring ch = s.Substring(i, 1);\n\t\t\tint c = ch.ToAscii();\n\t\t\tif (c == 34)",
                "\t\tint n = s.Length();\n\t\tif (n > 100) { n = 100; }\n\t\tint i = 0;\n\t\twhile (i < n)\n\t\t{\n\t\t\tstring ch = s.Substring(i, 1);\n\t\t\tint c = ch.ToAscii();\n\t\t\tif (c == 34)",
                "M9",
            ),
            # Del orquestador: WireText corta la cadena antes de recorrerla
            (
                "scripts/3_Game/DSBX_Wire.c",
                "static string WireText(string s)\n\t{\n",
                "static string WireText(string s)\n\t{\n\t\tif (s.Length() > 100) { s = s.Substring(0, 100); }\n",
                "M9",
            ),
            # Sol C-03: ValidHello con la condicion de ok invertida
            (
                "scripts/3_Game/DSBX_Messages.c",
                "\t\tif (!resp.ok)\n\t\t{\n\t\t\treturn false;\n\t\t}\n\t\tif (!IsHex(resp.session, 16))",
                "\t\tif (resp.ok)\n\t\t{\n\t\t\treturn false;\n\t\t}\n\t\tif (!IsHex(resp.session, 16))",
                "M6",
            ),
            # Sol C-03: ValidPoll sin rechazar mas de una orden
            (
                "scripts/3_Game/DSBX_Messages.c",
                "if (resp.ops.Count() > 1)",
                "if (false)",
                "M6",
            ),
            # Sol r2 C-02: n acotado con una asignacion compuesta
            (
                "scripts/3_Game/DSBX_Wire.c",
                "\t\tint n = s.Length();\n\t\tint i = 0;\n\t\twhile (i < n)\n\t\t{\n\t\t\tstring ch = s.Substring(i, 1);\n\t\t\tint c = ch.ToAscii();\n\t\t\tif (c == 34)",
                "\t\tint n = s.Length();\n\t\tif (n > 100) { n -= n - 100; }\n\t\tint i = 0;\n\t\twhile (i < n)\n\t\t{\n\t\t\tstring ch = s.Substring(i, 1);\n\t\t\tint c = ch.ToAscii();\n\t\t\tif (c == 34)",
                "M9",
            ),
            # Sol r2 C-02: el recorrido salta bytes
            (
                "scripts/3_Game/DSBX_Wire.c",
                "\t\t\t\toutStr = outStr + ch;\n\t\t\t}\n\t\t\ti = i + 1;\n",
                "\t\t\t\toutStr = outStr + ch;\n\t\t\t}\n\t\t\ti = i + 2;\n",
                "M9",
            ),
            # Brief en partida D-P3: el gancho del hueco se sale del #ifdef DIAG_DEVELOPER
            (
                "scripts/3_Game/DSBX_Peer.c",
                "#ifdef DIAG_DEVELOPER\n\t\t\tif (m_QaStepGapMs > 0",
                "\t\t\tif (m_QaStepGapMs > 0",
                "M13",
            ),
            # Sol r2 C-05: la guarda de sesion del acuse sin return
            (
                "scripts/3_Game/DSBX_Peer.c",
                "if (m_CatSendSession != m_CatSession)\n\t\t\t{\n\t\t\t\treturn;\n\t\t\t}\n\t\t\tm_CatFailures = 0;",
                "if (m_CatSendSession != m_CatSession)\n\t\t\t{\n\t\t\t}\n\t\t\tm_CatFailures = 0;",
                "M11",
            ),
            # C-01: el acuse de una pagina de otra sesion ya no se descarta
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\t{\n\t\t\tif (m_CatSendSession != m_CatSession)\n\t\t\t{\n\t\t\t\treturn;\n\t\t\t}\n\t\t\tm_CatFailures = 0;\n",
                "\t\t{\n\t\t\tm_CatFailures = 0;\n",
                "M11",
            ),
            # Revision Enforce MUST: DSBX_Peer deja de ser Managed (el m_Peer debil ya no pasa a null)
            (
                "scripts/3_Game/DSBX_Peer.c",
                "class DSBX_Peer : Managed\n",
                "class DSBX_Peer\n",
                "M14",
            ),
            # Revision Enforce MUST: el callback sujeta al peer con ref (el motor lo retiene para siempre)
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\tDSBX_Peer m_Peer;\n",
                "\tref DSBX_Peer m_Peer;\n",
                "M14",
            ),
            # Revision Enforce SHOULD: EffectGuard deja pasar una orden de otra sesion
            (
                "scripts/3_Game/DSBX_Peer.c",
                'if (order.session != m_Session)\n\t\t{\n\t\t\tm_GuardFailReason = "stale_session";\n\t\t\treturn false;\n\t\t}\n',
                "",
                "M7",
            ),
            # Revision Enforce SHOULD: EffectGuard deja pasar una orden de otra presentacion
            (
                "scripts/3_Game/DSBX_Peer.c",
                'if (order.conn != m_Conn)\n\t\t{\n\t\t\tm_GuardFailReason = "stale_conn";\n\t\t\treturn false;\n\t\t}\n',
                "",
                "M7",
            ),
            # Revision Enforce SHOULD: el 4xx vuelve a mirarse con el simbolo del enum (vale 6: casa un 500)
            (
                "scripts/3_Game/DSBX_Peer.c",
                "errorCode == DSBX_Const.REST_STATE_4XX)",
                "errorCode == ERestResultState.EREST_ERROR_CLIENTERROR)",
                "M11",
            ),
            # Revision Enforce SHOULD: el estado medido del 4xx cambia de valor
            (
                "scripts/3_Game/DSBX_Const.c",
                "const int REST_STATE_4XX = 5;",
                "const int REST_STATE_4XX = 6;",
                "M11",
            ),
            # Revision Enforce SHOULD: el canal R mira el estado 4xx
            (
                "scripts/3_Game/DSBX_Peer.c",
                "void OnChannelRError(int kind, float now)\n\t{",
                "void OnChannelRError(int kind, float now)\n\t{\n\t\tif (DSBX_Const.REST_STATE_4XX == 0) { return; }",
                "M11",
            ),
            # Revision Enforce SHOULD: ValidOrder vuelve a rechazar una orden sin args (dos conductas)
            (
                "scripts/3_Game/DSBX_Messages.c",
                "\t\tif (order.issued_ms < 0)\n",
                "\t\tif (!order.args)\n\t\t{\n\t\t\treturn false;\n\t\t}\n\t\tif (order.issued_ms < 0)\n",
                "M6",
            ),
            # Revision Enforce SHOULD: un fallo vuelve a retirar el callback sin cuarentena
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\t\tQuarantine(cb, canal);\n\t\t\treturn;\n",
                "\t\t\tcb.Retire();\n\t\t\treturn;\n",
                "M15",
            ),
            # Revision Enforce SHOULD: AcquireCallback ya no reutiliza la cuarentena
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\tif (!cb)\n\t\t{\n\t\t\tcb = TakeFromQuarantine(canal);\n\t\t}\n",
                "",
                "M15",
            ),
            # Revision Enforce SHOULD: la cuarentena se reutiliza sin esperar
            (
                "scripts/3_Game/DSBX_Peer.c",
                "if (!oldest || (NowMs() - oldest.m_RetiredMs) < DSBX_Const.CALLBACK_QUARANTINE_MS)",
                "if (!oldest)",
                "M15",
            ),
            # Revision Enforce SHOULD: el vigilante de P vuelve a retirar sin cuarentena
            (
                "scripts/3_Game/DSBX_Peer.c",
                "Quarantine(cb, DSBX_Const.CH_P);",
                "cb.Retire();",
                "M15",
            ),
            # Revision Enforce SHOULD: cuarentena tan corta como el vigilante
            (
                "scripts/3_Game/DSBX_Const.c",
                "const int CALLBACK_QUARANTINE_MS = 60000;",
                "const int CALLBACK_QUARANTINE_MS = 6000;",
                "M15",
            ),
            # Revision Enforce SHOULD: Shutdown no suelta los callbacks en cuarentena
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\tDetachAll(m_QuarantineP);\n",
                "",
                "M15",
            ),
            # Sol E-01: la cuarentena no guarda el callback
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\t\tquarantine.Insert(cb);\n",
                "",
                "M15",
            ),
            # Sol E-01: se extrae de la cuarentena pero no se devuelve
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\treturn oldest;\n",
                "\t\treturn null;\n",
                "M15",
            ),
            # Sol E-01: DetachAll no desliga el peer
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\t\t\titem.Detach();\n",
                "",
                "M15",
            ),
            # Tope de la cuarentena por debajo de lo que acumula un periodo con el backend caido
            (
                "scripts/3_Game/DSBX_Const.c",
                "const int CALLBACK_QUARANTINE_MAX = 64;",
                "const int CALLBACK_QUARANTINE_MAX = 32;",
                "M15",
            ),
            # Sol E-02: el veto de los 60 s sin su return (se reutiliza antes de tiempo)
            (
                "scripts/3_Game/DSBX_Peer.c",
                "if (!oldest || (NowMs() - oldest.m_RetiredMs) < DSBX_Const.CALLBACK_QUARANTINE_MS)\n\t\t{\n\t\t\treturn null;\n\t\t}\n",
                "if (!oldest || (NowMs() - oldest.m_RetiredMs) < DSBX_Const.CALLBACK_QUARANTINE_MS)\n\t\t{\n\t\t}\n",
                "M15",
            ),
            # Sol E-03: DetachAll se salta el primer callback
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\tint k = 0;\n\t\twhile (k < callbacks.Count())\n",
                "\t\tint k = 1;\n\t\twhile (k < callbacks.Count())\n",
                "M15",
            ),
            # Sol E-03: el incremento antes de Get(k) (tambien se salta el primero)
            (
                "scripts/3_Game/DSBX_Peer.c",
                "\t\t\tDSBX_Callback item = callbacks.Get(k);\n\t\t\tif (item)\n\t\t\t{\n\t\t\t\titem.Detach();\n\t\t\t}\n\t\t\tk = k + 1;\n",
                "\t\t\tk = k + 1;\n\t\t\tDSBX_Callback item = callbacks.Get(k);\n\t\t\tif (item)\n\t\t\t{\n\t\t\t\titem.Detach();\n\t\t\t}\n",
                "M15",
            ),
        ]
        for rel_file, old, new, expected_rule in cases:
            with self.subTest(rule=expected_rule, file=rel_file):
                self._assert_only_rule_fails(rel_file, old, new, expected_rule)

        # (w) M12: un CRLF
        with tempfile.TemporaryDirectory() as tmp:
            copy_dir = Path(tmp) / "DayZSandbox"
            shutil.copytree(REAL_MOD_DIR, copy_dir)
            target = copy_dir / "scripts/3_Game/DSBX_Const.c"
            target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n", 1))
            failed = [name for name, fn in ALL_CHECKS.items() if fn(copy_dir)]
            self.assertEqual(failed, ["M12"])


if __name__ == "__main__":
    unittest.main()
