"""Contrato de cable, payload generico, qa_fault fijo y sello de sonda (brief F0.3-0 §2.2)."""

import hashlib
import json
import math
import re
from pathlib import Path

WIRE_CAP = 3500
# D10 (brief F0.3-0 v4.5.5, §15): la sonda corta en 1023 caracteres las cadenas que LEE (medido en la partida diag;
# causa en hipotesis: JsonSerializer.ReadFromString). Ninguna cadena de los args de una orden (sk, sv, scol, scell)
# pasa de MAX_ARG_STR_CHARS. Los resultados que escribe la sonda no estan afectados, asi que la regla no vive en
# validate_payload (que tambien valida resultados) sino en check_arg_strings, que aplican el bridge y el peer falso.
MAX_ARG_STR_CHARS = 1000
QA_FAULT_LEN = 24
QA_FAULT_NONE = "_" * QA_FAULT_LEN
STAMP_REL_PATH = "scripts/5_Mission/DSBX_QA_Stamp.c"
REAL_PROBE_DIR = Path(__file__).resolve().parent / "probe" / "DayZSandbox_QA"

PAYLOAD_KEYS = ("sk", "sv", "nk", "nv", "ncol", "ncell", "scol", "scell", "rows")

EMPTY_PAYLOAD = {
    "sk": [],
    "sv": [],
    "nk": [],
    "nv": [],
    "ncol": [],
    "ncell": [],
    "scol": [],
    "scell": [],
    "rows": 0,
}

_QA_FAULT_CODE_RE = re.compile(r"^[a-z0-9_]*[a-z0-9]$", re.ASCII)


def empty_payload():
    return {
        "sk": [],
        "sv": [],
        "nk": [],
        "nv": [],
        "ncol": [],
        "ncell": [],
        "scol": [],
        "scell": [],
        "rows": 0,
    }


def format_qa_fault(fault=None):
    if fault is None or fault == "" or fault == QA_FAULT_NONE:
        return QA_FAULT_NONE
    if not isinstance(fault, str) or not (1 <= len(fault) <= QA_FAULT_LEN):
        raise ValueError(f"invalid qa_fault length: {fault!r}")
    if not _QA_FAULT_CODE_RE.fullmatch(fault):
        raise ValueError(f"invalid qa_fault format: {fault!r}")
    return fault.ljust(QA_FAULT_LEN, "_")


def parse_qa_fault(raw):
    if not isinstance(raw, str) or len(raw) != QA_FAULT_LEN or not raw.isascii():
        raise ValueError(f"qa_fault wire value must be {QA_FAULT_LEN} ASCII chars")
    return raw.rstrip("_")


def _check_key_list(arr, field_name):
    if not isinstance(arr, list):
        raise ValueError(f"{field_name} must be a list")
    seen = set()
    for item in arr:
        if not isinstance(item, str) or item == "":
            raise ValueError(f"{field_name} keys must be non-empty str")
        if item in seen:
            raise ValueError(f"duplicate key {item!r} in {field_name}")
        seen.add(item)
    return seen


def _check_str_list(arr, field_name):
    if not isinstance(arr, list):
        raise ValueError(f"{field_name} must be a list")
    for item in arr:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} values must be str")


def _check_num_list(arr, field_name):
    if not isinstance(arr, list):
        raise ValueError(f"{field_name} must be a list")
    for item in arr:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ValueError(f"{field_name} values must be finite int or float")


def check_arg_strings(args):
    """D10: ValueError si alguna cadena de sk, sv, scol o scell de unos args de orden pasa de MAX_ARG_STR_CHARS."""
    for field in ("sk", "sv", "scol", "scell"):
        for s in (args or {}).get(field) or []:
            if isinstance(s, str) and len(s) > MAX_ARG_STR_CHARS:
                raise ValueError(f"arg string longer than {MAX_ARG_STR_CHARS} chars in {field} ({len(s)})")


def validate_payload(obj):
    if not isinstance(obj, dict):
        raise ValueError("payload must be a dict")
    for key in PAYLOAD_KEYS:
        if key not in obj:
            raise ValueError(f"missing payload key {key!r}")

    rows = obj["rows"]
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
        raise ValueError("rows must be a non-negative int")

    sk = obj["sk"]
    sv = obj["sv"]
    nk = obj["nk"]
    nv = obj["nv"]
    ncol = obj["ncol"]
    ncell = obj["ncell"]
    scol = obj["scol"]
    scell = obj["scell"]

    sk_set = _check_key_list(sk, "sk")
    _check_str_list(sv, "sv")
    nk_set = _check_key_list(nk, "nk")
    _check_num_list(nv, "nv")
    ncol_set = _check_key_list(ncol, "ncol")
    _check_num_list(ncell, "ncell")
    scol_set = _check_key_list(scol, "scol")
    _check_str_list(scell, "scell")

    if len(sk) != len(sv):
        raise ValueError("sk and sv lengths differ")
    if len(nk) != len(nv):
        raise ValueError("nk and nv lengths differ")
    if not sk_set.isdisjoint(nk_set):
        raise ValueError("sk and nk must be disjoint")
    if not ncol_set.isdisjoint(scol_set):
        raise ValueError("ncol and scol must be disjoint")
    if rows > 0 and (len(ncol) + len(scol) == 0):
        raise ValueError("rows > 0 requires at least one column")
    if len(ncell) != rows * len(ncol):
        raise ValueError("ncell length does not match rows * len(ncol)")
    if len(scell) != rows * len(scol):
        raise ValueError("scell length does not match rows * len(scol)")

    if "qa_fault" in sk_set:
        qf_val = sv[sk.index("qa_fault")]
        if not isinstance(qf_val, str) or len(qf_val) != QA_FAULT_LEN or not qf_val.isascii():
            raise ValueError(f"qa_fault value must be {QA_FAULT_LEN} ASCII chars")


def pack_payload(
    scalars_str=None,
    scalars_num=None,
    num_cols=None,
    str_cols=None,
    row_dicts=None,
):
    if scalars_str is not None and not isinstance(scalars_str, dict):
        raise ValueError("scalars_str must be dict or None")
    if scalars_num is not None and not isinstance(scalars_num, dict):
        raise ValueError("scalars_num must be dict or None")
    if num_cols is not None and not isinstance(num_cols, (list, tuple)):
        raise ValueError("num_cols must be list, tuple or None")
    if str_cols is not None and not isinstance(str_cols, (list, tuple)):
        raise ValueError("str_cols must be list, tuple or None")
    if row_dicts is not None and not isinstance(row_dicts, (list, tuple)):
        raise ValueError("row_dicts must be list, tuple or None")

    sk = list(scalars_str.keys()) if scalars_str else []
    sv = list(scalars_str.values()) if scalars_str else []
    nk = list(scalars_num.keys()) if scalars_num else []
    nv = list(scalars_num.values()) if scalars_num else []
    ncol = list(num_cols) if num_cols else []
    scol = list(str_cols) if str_cols else []

    ncol_set = _check_key_list(ncol, "ncol")
    scol_set = _check_key_list(scol, "scol")
    if not ncol_set.isdisjoint(scol_set):
        raise ValueError("ncol and scol must be disjoint")

    expected_cols = ncol_set | scol_set
    r_list = list(row_dicts) if row_dicts is not None else []
    rows = len(r_list)
    ncell = []
    scell = []
    for row in r_list:
        if not isinstance(row, dict) or set(row.keys()) != expected_cols:
            raise ValueError("row dict keys do not match declared columns")
        for col in ncol:
            ncell.append(row[col])
        for col in scol:
            scell.append(row[col])

    out = {
        "sk": sk,
        "sv": sv,
        "nk": nk,
        "nv": nv,
        "ncol": ncol,
        "ncell": ncell,
        "scol": scol,
        "scell": scell,
        "rows": rows,
    }
    validate_payload(out)
    return out


def unpack_payload(obj):
    validate_payload(obj)
    ncol = list(obj["ncol"])
    scol = list(obj["scol"])
    ncell = obj["ncell"]
    scell = obj["scell"]
    rows_count = obj["rows"]
    n_nc = len(ncol)
    n_sc = len(scol)
    rows_out = []
    for r_idx in range(rows_count):
        row = {}
        n_base = r_idx * n_nc
        for c_idx, col in enumerate(ncol):
            row[col] = ncell[n_base + c_idx]
        s_base = r_idx * n_sc
        for c_idx, col in enumerate(scol):
            row[col] = scell[s_base + c_idx]
        rows_out.append(row)
    return {
        "str": dict(zip(obj["sk"], obj["sv"])),
        "num": dict(zip(obj["nk"], obj["nv"])),
        "ncol": ncol,
        "scol": scol,
        "rows": rows_out,
    }


def _compact_json_bytes(data):
    if isinstance(data, dict) and "now_ms" in data:
        now_val = data["now_ms"]
        if isinstance(now_val, bool) or not isinstance(now_val, (int, float)) or not math.isfinite(now_val):
            raise ValueError("now_ms must be finite number")
    return json.dumps(data, allow_nan=False, separators=(",", ":")).encode("utf-8")


def order_wire_bytes(order):
    return _compact_json_bytes(order)


def poll_wire_bytes(order, now_ms=99999999.999):
    return _compact_json_bytes({"now_ms": now_ms, "ops": [order]})


def result_wire_bytes(result):
    return _compact_json_bytes(result)


def compute_probe_stamp_from_pairs(pairs):
    filtered = []
    for rel, content in pairs:
        norm = str(rel).replace("\\", "/").lstrip("/")
        if norm == STAMP_REL_PATH:
            continue
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError("content must be bytes")
        filtered.append((norm, bytes(content)))
    filtered.sort(key=lambda item: item[0])
    h = hashlib.sha256()
    for norm, content in filtered:
        h.update(norm.encode("utf-8"))
        h.update(b"\x00")
        h.update(content)
        h.update(b"\x00")
    return h.hexdigest()[:16]


def compute_probe_stamp(probe_dir=REAL_PROBE_DIR):
    root = Path(probe_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"probe directory not found: {root}")
    pairs = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == STAMP_REL_PATH:
            continue
        pairs.append((rel, path.read_bytes()))
    return compute_probe_stamp_from_pairs(pairs)
