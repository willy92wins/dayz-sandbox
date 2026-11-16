"""Plan de escena, expectativa, validacion previa, envolvente y predicados (F2-offline §3 y §4).

Funciones puras, sin red ni estado global. Solo biblioteca estandar.
Contrato: plans/2026-11-14-m1-f2-offline-brief.md v1.2.2, §2 (D1-D12), §3, §4.1-§4.3
y §13 (A2, A3, A6), con el delta del contrato v1.3 del cable `dsbx1`
(plans/2026-11-15-m1-f2-partida-brief.md §2, DP-1 a DP-5, y §3): enteros y columnas.

Contrato v1.3 (tanda T1):
- `build_plan` produce los `args` de §3.2 con **todas** las claves (DP-2): `f2: 1`, `doc_id`,
  `rev`, `hash`, `plan_sha256`, `caps` con `{objeto, infectado, animal, total}` (`total = -1`
  si la biblioteca no lo fija), `classes` y las columnas `lid`, `ci`, `x_mm`, `z_mm` y
  `yaw_mdeg`, de la misma longitud y en el orden del documento.
- `plan_sha256` es el SHA-256 del JSON canonico de
  `{doc_id, rev, hash, classes, lid, ci, x_mm, z_mm, yaw_mdeg}` (§3.2).
- Unidades (§3.1): `x_mm = round(x * 1000)` con el `round` de Python (mitad al par) y
  `yaw_mdeg = round(yaw * 1000) % 360000`, normalizado despues de redondear.
- La expectativa (D11) y los predicados trabajan en mm: `EPS_Q` = 2 mm y `POS_TOL` = 500 mm.
  La expectativa no pasa por el constructor del plan: es `x * 1000.0` sin redondear.
- Las filas de las lecturas (§3.6) solo admiten enteros; un float o un bool las invalida.
- La API HTTP sigue en metros (§3.8): `obs_now_row_to_m` convierte las filas `now` al recibir.
- Un plan v1.2.2 (`rows`) no pasa `valid_plan_args`, y el mundo falso lo rechaza (`bad_plan`).

Decisiones donde el brief no alcanza (anotadas tambien en los recibos):
- `valid_op_id` acepta `(op|rd)-<1..6 digitos>`; el prefijo `rd-` es el de las internas
  de §4.5.
- `compute_envelope` usa el maximo normativo 999999 para `ci` de las filas de checkpoint y
  99 999 000 mm para `x_mm` y `z_mm`; el cuerpo que decide el tope es `observe now`.
- En el predicado de «apply detenido», si `scene.pending` sigue siendo la orden se
  devuelve `("unresolved", None)`: la orden no esta resuelta y toca compensar (§4.5).
- `validate_for_apply` acepta `op_id` y `conn` opcionales para medir la envolvente con
  sus valores reales; si no se pasan, usa el maximo normativo (`op-999999`, 999999).
- `build_plan` sin `caps` validos lanza `ValueError`: no hay orden completa que mandar
  (DP-2, A6). `validate_for_apply` ya para antes con `budget_exceeded`.
"""
import copy
import hashlib
import json
import math
import re

from app.backend.bridge import WIRE_CAP, valid_world_read

# Tolerancias de D12 en mm (§3.1 del brief de F2-partida): POS_TOL_M = 500 mm y EPS_Q = 2 mm.
POS_TOL = 500
EPS_Q = 2
POS_TOL_M = POS_TOL  # nombre del brief (§3.1); desde v1.3 el valor va en mm
SCENE_BATCH = 8

NON_ACTOR_KINDS = ("objeto", "infectado", "animal")
KIND_BY_PREFIX = {
    "obj": "objeto",
    "zmb": "infectado",
    "ani": "animal",
}
HTTP_STATUS = {
    "expansion_unavailable": 422,
    "catalog_pending": 409,
    "unknown_class": 422,
    "out_of_map": 422,
    "budget_exceeded": 422,
    "plan_too_large": 422,
}

# Forma v1.3 de los args de scene.apply (§3.2): todas las claves siempre (DP-2).
PLAN_COLUMNS = ("lid", "ci", "x_mm", "z_mm", "yaw_mdeg")
PLAN_KEYS = ("f2", "doc_id", "rev", "hash", "plan_sha256", "caps", "classes") + PLAN_COLUMNS
CAPS_KEYS = ("objeto", "infectado", "animal", "total")
CAPS_TOTAL_NONE = -1  # valor neutro explicito: la biblioteca no fija total (DP-2)

_DOC_ID_RE = re.compile(r"d-[0-9a-f]{8}")
_LID_RE = re.compile(r"(obj|zmb|ani)-(0[1-9]|[1-9][0-9]+)")
_HEX16_RE = re.compile(r"[0-9a-fA-F]{16}")
_HEX64_RE = re.compile(r"[0-9a-fA-F]{64}")
_OP_ID_RE = re.compile(r"(op|rd)-([0-9]{1,6})")
_MAX_COUNT = 999999
_MAX_REV = 999999999
_MAX_WORLD_SIZE = 99999
# Rangos v1.3 de las filas (§3.6), en enteros
MAX_XZ_MM = 99999000  # world_size <= 99999 m; cabe en un int de 32 bits
MAX_Y_MM = 9999999  # y_mm y gy_mm en [-9 999 999, 9 999 999]
YAW_MDEG_MOD = 360000  # yaw_mdeg en [0, 360000)
MAX_HP_MILLI = 1000  # hp_milli en [0, 1000]
MAX_STRING_CHARS = 1023  # A15/M20: el motor corta cada cadena de un JSON leido


def _is_int(val):
    return isinstance(val, int) and not isinstance(val, bool)


def _is_num(val):
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def _is_count(val):
    return _is_int(val) and 0 <= val <= _MAX_COUNT


def _is_rev(val):
    return _is_int(val) and 0 <= val <= _MAX_REV


def _is_conn(val):
    return _is_int(val) and 0 <= val <= _MAX_COUNT


# --- Unidades del cable (§3.1) --------------------------------------------


def m_to_mm(val):
    """Metros -> milimetros enteros: `round(metros * 1000)` con el `round` de Python (§3.1)."""
    return round(float(val) * 1000)


def yaw_to_mdeg(val):
    """Grados -> milesimas de grado en [0, 360000): se normaliza despues de redondear (§3.1)."""
    return round(float(val) * 1000) % YAW_MDEG_MOD


def mm_to_m(val):
    """Milimetros (o milesimas) enteros -> metros (o unidades). `None` se queda en `None`."""
    if val is None:
        return None
    return val / 1000.0


def obs_now_row_to_m(row):
    """Fila `now` v1.3 -> la forma de la API (§3.8), en metros, grados y hp en [0, 1].

    `[lid, x_mm, y_mm, z_mm, yaw_mdeg, hp_milli, n_own, n_foreign]` ->
    `[lid, x, y, z, yaw, hp, n_own, n_foreign]`. Los nulos de M15 se quedan nulos.
    """
    lid, x, y, z, yaw, hp, n_own, n_foreign = row
    return [lid, mm_to_m(x), mm_to_m(y), mm_to_m(z), mm_to_m(yaw), mm_to_m(hp), n_own, n_foreign]


def obs_checkpoint_row_to_m(row):
    """Fila de checkpoint v1.3 -> metros y grados: `[lid, ci, x, y, z, yaw, gy]`."""
    lid, ci, x, y, z, yaw, gy = row
    return [lid, ci, mm_to_m(x), mm_to_m(y), mm_to_m(z), mm_to_m(yaw), mm_to_m(gy)]


# --- Identificadores --------------------------------------------------------


def valid_lid(lid):
    """Comprueba que un lid cumpla el patron del esquema, con digitos ASCII y <= 10 caracteres (§3.6)."""
    return (
        isinstance(lid, str)
        and len(lid) <= 10
        and _LID_RE.fullmatch(lid) is not None
    )


def valid_doc_id(doc_id):
    """Comprueba que doc_id cumpla el patron del esquema (d-[0-9a-f]{8})."""
    return isinstance(doc_id, str) and _DOC_ID_RE.fullmatch(doc_id) is not None


def valid_op_id(op_id):
    """Comprueba que el numero de un op_id de la orden tenga 6 digitos como mucho (§3.6)."""
    return isinstance(op_id, str) and _OP_ID_RE.fullmatch(op_id) is not None


def canonical_json_bytes(obj):
    """JSON canonico UTF-8: sort_keys=True, separadores ',' y ':'."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compact_json_bytes(obj):
    """JSON compacto UTF-8 con separadores ',' y ':'."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# --- Expectativa, caps y plan ----------------------------------------------


def extract_expectation(doc):
    """Extrae directamente del documento congelado {lid: (cls, x_mm, z_mm)} de cada entidad no actor (D11).

    En mm (v1.3), pero sin pasar por el constructor del plan ni redondear: `x * 1000.0`.
    """
    if not isinstance(doc, dict):
        return {}
    out = {}
    for ent in doc.get("entities") or ():
        if not isinstance(ent, dict):
            continue
        if ent.get("kind") == "actor":
            continue
        lid = ent.get("id")
        cls = ent.get("cls")
        x = ent.get("x")
        z = ent.get("z")
        if isinstance(lid, str) and isinstance(cls, str) and _is_num(x) and _is_num(z):
            out[lid] = (cls, float(x) * 1000.0, float(z) * 1000.0)
    return out


def extract_caps(store_catalog):
    """Extrae caps {objeto, infectado, animal[, total]} del catalogo del Store (§3.3).

    Falla cerrado (A6): sin los tres topes por tipo como enteros no negativos, devuelve None.
    No inventa valores ni fuerza tipos.
    """
    if not isinstance(store_catalog, dict):
        return None
    raw = store_catalog.get("caps")
    if not isinstance(raw, dict):
        return None
    caps = {}
    for kind in NON_ACTOR_KINDS:
        val = raw.get(kind)
        if not _is_int(val) or val < 0:
            return None
        caps[kind] = val
    if "total" in raw:
        val = raw["total"]
        if not _is_int(val) or val < 0:
            return None
        caps["total"] = val
    return caps


def wire_caps(caps):
    """`caps` del cable v1.3: siempre las cuatro claves, con `total = -1` si no hay total (DP-2)."""
    out = {kind: caps[kind] for kind in NON_ACTOR_KINDS}
    out["total"] = caps["total"] if "total" in caps else CAPS_TOTAL_NONE
    return out


def plan_sha256_of(plan):
    """SHA-256 del JSON canonico de {doc_id, rev, hash, classes, lid, ci, x_mm, z_mm, yaw_mdeg} (§3.2)."""
    core = {key: plan[key] for key in ("doc_id", "rev", "hash", "classes") + PLAN_COLUMNS}
    return hashlib.sha256(canonical_json_bytes(core)).hexdigest()


def build_plan(doc, rev, hash_, store_catalog):
    """Construye los args v1.3 de scene.apply (§3.2) a partir del documento congelado.

    Todas las claves siempre (DP-2). Sin `caps` validos no hay orden completa: `ValueError`.
    """
    caps = extract_caps(store_catalog)
    if caps is None:
        raise ValueError("build_plan: sin caps validos no hay orden completa (DP-2, A6)")
    doc_id = doc["doc_id"]
    non_actors = [
        ent for ent in (doc.get("entities") or ())
        if isinstance(ent, dict) and ent.get("kind") in NON_ACTOR_KINDS
    ]
    classes = sorted({ent["cls"] for ent in non_actors})
    ci_map = {cls: idx for idx, cls in enumerate(classes)}
    plan = {
        "f2": 1,
        "doc_id": doc_id,
        "rev": int(rev),
        "hash": hash_,
        "plan_sha256": None,
        "caps": wire_caps(caps),
        "classes": classes,
        "lid": [ent["id"] for ent in non_actors],
        "ci": [ci_map[ent["cls"]] for ent in non_actors],
        "x_mm": [m_to_mm(ent["x"]) for ent in non_actors],
        "z_mm": [m_to_mm(ent["z"]) for ent in non_actors],
        "yaw_mdeg": [yaw_to_mdeg(ent["yaw"]) for ent in non_actors],
    }
    plan["plan_sha256"] = plan_sha256_of(plan)
    return plan


def plan_args_error(plan):
    """Comprueba la forma v1.3 de los args de scene.apply (§3.2, DP-2).

    Devuelve `None` si valen, o el pointer (`/plan/<clave>`) del primer fallo. Exige
    exactamente las claves de `PLAN_KEYS`, `f2` = 1, `caps` con sus cuatro claves y las
    columnas de la misma longitud, solo con enteros donde toca.
    """
    if not isinstance(plan, dict):
        return "/plan"
    for key in PLAN_KEYS:
        if key not in plan:
            return "/plan/%s" % key
    for key in plan:
        if key not in PLAN_KEYS:
            return "/plan/%s" % key
    if not (_is_int(plan["f2"]) and plan["f2"] == 1):
        return "/plan/f2"
    if not valid_doc_id(plan["doc_id"]):
        return "/plan/doc_id"
    if not _is_rev(plan["rev"]):
        return "/plan/rev"
    for key in ("hash", "plan_sha256"):
        val = plan[key]
        if not isinstance(val, str) or _HEX64_RE.fullmatch(val) is None:
            return "/plan/%s" % key
    caps = plan["caps"]
    if not isinstance(caps, dict) or set(caps) != set(CAPS_KEYS):
        return "/plan/caps"
    for kind in NON_ACTOR_KINDS:
        if not _is_int(caps[kind]) or caps[kind] < 0:
            return "/plan/caps/%s" % kind
    if not _is_int(caps["total"]) or caps["total"] < CAPS_TOTAL_NONE:
        return "/plan/caps/total"
    classes = plan["classes"]
    if not isinstance(classes, list) or not all(isinstance(c, str) for c in classes):
        return "/plan/classes"
    cols = [plan[key] for key in PLAN_COLUMNS]
    for key, col in zip(PLAN_COLUMNS, cols):
        if not isinstance(col, list):
            return "/plan/%s" % key
    n = len(cols[0])
    for key, col in zip(PLAN_COLUMNS, cols):
        if len(col) != n:
            return "/plan/%s" % key
    for lid, ci, x, z, yaw in zip(*cols):
        if not isinstance(lid, str):
            return "/plan/lid"
        if not _is_int(ci) or ci < 0 or ci >= len(classes):
            return "/plan/ci"
        if not _is_int(x):
            return "/plan/x_mm"
        if not _is_int(z):
            return "/plan/z_mm"
        if not _valid_yaw_mdeg(yaw):
            return "/plan/yaw_mdeg"
    return None


def valid_plan_args(plan):
    """True si los args de scene.apply tienen la forma v1.3 completa (DP-2)."""
    return plan_args_error(plan) is None


# --- Envolvente (§3.6 de F2b y §3.7 del brief de F2-partida) ----------------


def _worst_generation(op_id="op-999999"):
    return {
        "session": "0" * 16,
        "op_id": op_id,
        "rev": _MAX_REV,
        "hash": "0" * 64,
        "plan_sha256": "0" * 64,
    }


def _worst_read_base(doc_id="d-00000000", max_retained=True, op_id="op-999999"):
    retained = ["obj-999999"] * 8 if max_retained else []
    retained_n = _MAX_COUNT if max_retained else 0
    pending = {"session": "0" * 16, "op_id": op_id, "n": _MAX_COUNT} if max_retained else None
    outcome = "compensated" if max_retained else "done"
    return {
        "epoch": "0" * 32,
        "generation": _worst_generation(op_id),
        "registry_n": _MAX_COUNT,
        "registry_sha256": "0" * 64,
        "scene": {
            "doc_id": doc_id,
            "gen_n": _MAX_COUNT,
            "n": _MAX_COUNT,
            "retained_n": retained_n,
            "retained": retained,
            "pending": pending,
            "last": {
                "session": "0" * 16,
                "op_id": op_id,
                "verb": "scene.apply",
                "outcome": outcome,
            },
        },
    }


def _envelope_caps(caps):
    """caps de la envolvente: los valores reales de la orden; lo que falte, con su cota."""
    src = caps if isinstance(caps, dict) else {}
    out = {}
    for kind in NON_ACTOR_KINDS:
        val = src.get(kind)
        out[kind] = val if _is_int(val) else _MAX_COUNT
    total = src.get("total")
    out["total"] = total if _is_int(total) else CAPS_TOTAL_NONE
    return out


def compute_envelope(lids, classes, caps=None, doc_id="d-00000000", rev=_MAX_REV,
                     hash_="0" * 64, op_id="op-999999", conn=_MAX_COUNT,
                     session="0" * 16, epoch="0" * 32, inst="0" * 32):
    """Calcula la envolvente de bytes UTF-8 de los 4 cuerpos de §3.6, con las formas v1.3.

    Usa los valores reales de la orden (`lid`, clases, `rev`, `op_id`, `conn`, `caps`,
    `doc_id`, `hash`) y los maximos normativos v1.3 solo para lo que pone el mod (A3):
    `x_mm`/`z_mm` 99 999 000, `y_mm`/`gy_mm` -9 999 999, `yaw_mdeg` 359 999, `hp_milli`
    1000 y contadores 999 999.
    """
    caps_obj = _envelope_caps(caps)
    sorted_classes = sorted(set(classes))
    ci_max = max(len(sorted_classes) - 1, 0)
    norm_lids = []
    ckpt_rows = []
    now_rows = []
    for lid in lids:
        norm_lid = lid if isinstance(lid, str) else "obj-999999"
        norm_lids.append(norm_lid)
        ckpt_rows.append([norm_lid, _MAX_COUNT, MAX_XZ_MM, -MAX_Y_MM, MAX_XZ_MM,
                          YAW_MDEG_MOD - 1, -MAX_Y_MM])
        now_rows.append([norm_lid, MAX_XZ_MM, -MAX_Y_MM, MAX_XZ_MM, YAW_MDEG_MOD - 1,
                         MAX_HP_MILLI, _MAX_COUNT, _MAX_COUNT])
    n = len(norm_lids)

    args = {
        "f2": 1,
        "doc_id": doc_id,
        "rev": rev,
        "hash": hash_,
        "plan_sha256": "0" * 64,
        "caps": caps_obj,
        "classes": sorted_classes,
        "lid": norm_lids,
        "ci": [ci_max] * n,
        "x_mm": [MAX_XZ_MM] * n,
        "z_mm": [MAX_XZ_MM] * n,
        "yaw_mdeg": [YAW_MDEG_MOD - 1] * n,
    }
    poll_body = {
        "ok": True,
        "now_ms": 999999999999,
        "ops": [{
            "op_id": op_id,
            "session": session,
            "conn": conn,
            "epoch": epoch,
            "inst": inst,
            "verb": "scene.apply",
            "args": args,
            "issued_ms": 999999999999,
            "ttl_ms": 99999999,
        }],
    }
    poll_apply_bytes = len(compact_json_bytes(poll_body))

    # Cota superior del envoltorio /result con un reason de longitud maxima
    worst_reason = "foreign_content_retained_000000"
    read_apply = _worst_read_base(doc_id=doc_id, max_retained=False, op_id=op_id)
    read_apply["obs"] = {"at": "checkpoint", "rows": ckpt_rows}
    res_apply_body = {
        "op_id": op_id,
        "session": session,
        "epoch": epoch,
        "status": "done",
        "reason": worst_reason,
        "dup": False,
        "read": read_apply,
    }
    apply_result_bytes = len(compact_json_bytes(res_apply_body))

    read_reset = _worst_read_base(doc_id=doc_id, max_retained=True, op_id=op_id)
    res_reset_body = {
        "op_id": op_id,
        "session": session,
        "epoch": epoch,
        "status": "done",
        "reason": worst_reason,
        "dup": False,
        "read": read_reset,
    }
    reset_result_bytes = len(compact_json_bytes(res_reset_body))

    read_obs = copy.deepcopy(read_reset)
    read_obs["obs"] = {"at": "now", "rows": now_rows}
    res_obs_body = {
        "op_id": "rd-999999",
        "session": session,
        "epoch": epoch,
        "status": "done",
        "reason": worst_reason,
        "dup": False,
        "read": read_obs,
    }
    observe_now_bytes = len(compact_json_bytes(res_obs_body))

    return {
        "poll_apply": poll_apply_bytes,
        "result_apply": apply_result_bytes,
        "result_observe_now": observe_now_bytes,
        "result_reset_or_read": reset_result_bytes,
        "max_bytes": max(poll_apply_bytes, apply_result_bytes, observe_now_bytes, reset_result_bytes),
    }


def _make_error_response(code, errors):
    first = errors[0]
    return {
        "ok": False,
        "code": code,
        "http": HTTP_STATUS[code],
        "pointer": first["pointer"],
        "msg": first["msg"],
        "errors": errors,
    }


def _world_catalog_classes(world_catalog):
    if not isinstance(world_catalog, dict):
        return set()
    classes = world_catalog.get("classes")
    if not isinstance(classes, (list, tuple, set)):
        return set()
    out = set()
    for item in classes:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
            out.add(item[0])
    return out


def validate_for_apply(doc, rev, hash_, store_catalog, world_catalog=None,
                       catalog_valid=False, world_size=15360, wire_cap=WIRE_CAP,
                       op_id=None, conn=None):
    """Valida el documento congelado antes de mandar nada (§4.1), en el orden exacto de la tabla.

    Para en el primer codigo de error y devuelve la lista completa de errores de ese codigo en `errors`.
    Si todo pasa, devuelve {"ok": True, "plan": plan, "expectation": expectation, "envelope": env}.

    Falla cerrado (A6): `catalog_valid` es False por defecto, y sin `caps` validos la respuesta
    es `budget_exceeded`. `op_id` y `conn` son opcionales; si se pasan, se usan sus valores
    reales en la envolvente y se valida el numero del `op_id` (§3.6).
    """
    entities = doc.get("entities") if isinstance(doc, dict) else []
    if not isinstance(entities, list):
        entities = []

    # 1. expansion_unavailable (422): el documento tiene actores (D3)
    actor_errors = []
    for i, ent in enumerate(entities):
        if isinstance(ent, dict) and ent.get("kind") == "actor":
            actor_errors.append({
                "code": "expansion_unavailable",
                "pointer": f"/entities/{i}",
                "msg": f"La escena contiene actores ({ent.get('id', i)}) y F2 no dispone de motor de actores.",
            })
    if actor_errors:
        return _make_error_response("expansion_unavailable", actor_errors)

    # 2. catalog_pending (409): no hay catalogo del mundo valido para el servidor de ahora (D4)
    if not catalog_valid or world_catalog is None:
        return _make_error_response("catalog_pending", [{
            "code": "catalog_pending",
            "pointer": "",
            "msg": "No hay catalogo del mundo valido para el servidor actual.",
        }])

    # 3. unknown_class (422): una clase que no esta en ese catalogo
    known_classes = _world_catalog_classes(world_catalog)
    unknown_errors = []
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            continue
        cls = ent.get("cls")
        if cls not in known_classes:
            unknown_errors.append({
                "code": "unknown_class",
                "pointer": f"/entities/{i}/cls",
                "msg": f"La clase '{cls}' no existe en el catalogo del mundo.",
            })
    if unknown_errors:
        return _make_error_response("unknown_class", unknown_errors)

    # 4. out_of_map (422): x o z fuera de [0, world_size del hello]
    oom_errors = []
    wsize = float(world_size) if _is_num(world_size) else 0.0
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            continue
        for axis in ("x", "z"):
            val = ent.get(axis)
            if not _is_num(val) or float(val) < 0.0 or float(val) > wsize:
                oom_errors.append({
                    "code": "out_of_map",
                    "pointer": f"/entities/{i}/{axis}",
                    "msg": f"Coordenada {axis}={val} fuera de [0, {world_size}].",
                })
    if oom_errors:
        return _make_error_response("out_of_map", oom_errors)

    # 5. budget_exceeded (422): sin caps validos, cuentas por tipo > caps del Store,
    #    o total > caps.total. Falla cerrado (A6): sin topes no se inventan valores.
    caps = extract_caps(store_catalog)
    if caps is None:
        return _make_error_response("budget_exceeded", [{
            "code": "budget_exceeded",
            "pointer": "/entities",
            "msg": "El catalogo del Store no tiene caps validos para objeto, infectado y animal.",
        }])
    counts = {k: 0 for k in NON_ACTOR_KINDS}
    for ent in entities:
        if isinstance(ent, dict) and ent.get("kind") in counts:
            counts[ent["kind"]] += 1
    budget_errors = []
    for k in NON_ACTOR_KINDS:
        cap = caps.get(k)
        if counts[k] > cap:
            budget_errors.append({
                "code": "budget_exceeded",
                "pointer": "/entities",
                "msg": f"Presupuesto de '{k}' superado ({counts[k]} > {cap}).",
            })
    total_count = sum(counts.values())
    if "total" in caps and total_count > caps["total"]:
        budget_errors.append({
            "code": "budget_exceeded",
            "pointer": "/entities",
            "msg": f"Presupuesto total superado ({total_count} > {caps['total']}).",
        })
    if budget_errors:
        return _make_error_response("budget_exceeded", budget_errors)

    # 6. plan_too_large (422): un lid que no sea ASCII o tenga mas de 10 caracteres,
    #    una rev de mas de 9 digitos, un op_id de mas de 6, o la orden o la envolvente
    #    pasarian de WIRE_CAP.
    lids = []
    classes = []
    large_errors = []
    doc_id = doc.get("doc_id") if isinstance(doc, dict) else None
    if isinstance(doc_id, str) and len(doc_id) > MAX_STRING_CHARS:
        large_errors.append({
            "code": "plan_too_large",
            "pointer": "",
            "msg": f"El doc_id supera {MAX_STRING_CHARS} caracteres.",
        })
    for i, ent in enumerate(entities):
        if not isinstance(ent, dict):
            continue
        lid = ent.get("id")
        lids.append(lid if isinstance(lid, str) else "")
        cls = ent.get("cls")
        classes.append(cls if isinstance(cls, str) else "")
        if isinstance(lid, str) and len(lid) > MAX_STRING_CHARS:
            large_errors.append({
                "code": "plan_too_large",
                "pointer": f"/entities/{i}/id",
                "msg": f"El lid supera {MAX_STRING_CHARS} caracteres.",
            })
        if isinstance(cls, str) and len(cls) > MAX_STRING_CHARS:
            large_errors.append({
                "code": "plan_too_large",
                "pointer": f"/entities/{i}/cls",
                "msg": f"La clase supera {MAX_STRING_CHARS} caracteres.",
            })
        if not valid_lid(lid):
            large_errors.append({
                "code": "plan_too_large",
                "pointer": f"/entities/{i}/id",
                "msg": f"Identificador lid '{lid}' supera 10 caracteres o no cumple el patron ASCII.",
            })
    if not _is_rev(rev):
        large_errors.append({
            "code": "plan_too_large",
            "pointer": "",
            "msg": f"La revision '{rev}' no es un entero de 9 digitos como mucho.",
        })
    if op_id is not None and not valid_op_id(op_id):
        large_errors.append({
            "code": "plan_too_large",
            "pointer": "",
            "msg": f"El numero del op_id '{op_id}' supera 6 digitos.",
        })

    env = None
    plan = None
    if _is_int(rev):
        plan = build_plan(doc, rev, hash_, store_catalog)
        env = compute_envelope(
            lids, classes, caps=plan["caps"], doc_id=doc["doc_id"],
            rev=plan["rev"], hash_=hash_, op_id=(op_id or "op-999999"),
            conn=(conn if conn is not None else _MAX_COUNT),
        )
        actual_poll_body = {
            "ok": True,
            "now_ms": 999999999999,
            "ops": [{
                "op_id": op_id or "op-999999",
                "session": "0" * 16,
                "conn": conn if conn is not None else _MAX_COUNT,
                "epoch": "0" * 32,
                "inst": "0" * 32,
                "verb": "scene.apply",
                "args": plan,
                "issued_ms": 999999999999,
                "ttl_ms": 99999999,
            }],
        }
        actual_poll_len = len(compact_json_bytes(actual_poll_body))
        if actual_poll_len > wire_cap or env["max_bytes"] > wire_cap:
            large_errors.append({
                "code": "plan_too_large",
                "pointer": "",
                "msg": f"La envolvente ({max(actual_poll_len, env['max_bytes'])} B) supera WIRE_CAP ({wire_cap} B).",
            })
    if large_errors:
        return _make_error_response("plan_too_large", large_errors)

    expectation = extract_expectation(doc)
    return {
        "ok": True,
        "plan": plan,
        "expectation": expectation,
        "envelope": env,
    }


# --- Validacion de lecturas (§3.2 de F2b y §3.6 del brief de F2-partida) ----


def _xz_limit_mm(world_size):
    return min(float(world_size) * 1000.0, float(MAX_XZ_MM))


def _valid_xz_mm(val, world_size=_MAX_WORLD_SIZE):
    """`x_mm` y `z_mm`: enteros en [0, world_size * 1000] (y como mucho 99 999 000)."""
    if not _is_int(val):
        return False
    if not _is_num(world_size) or float(world_size) > float(_MAX_WORLD_SIZE):
        return False
    return 0 <= val <= _xz_limit_mm(world_size)


def _valid_y_mm(val):
    """`y_mm` y `gy_mm`: enteros en [-9 999 999, 9 999 999]."""
    return _is_int(val) and -MAX_Y_MM <= val <= MAX_Y_MM


def _valid_yaw_mdeg(val):
    """`yaw_mdeg`: entero en [0, 360000)."""
    return _is_int(val) and 0 <= val < YAW_MDEG_MOD


def _valid_hp_milli(val):
    """`hp_milli`: entero en [0, 1000]."""
    return _is_int(val) and 0 <= val <= MAX_HP_MILLI


def valid_obs_checkpoint_row(row, world_size=_MAX_WORLD_SIZE):
    """Valida una fila de obs checkpoint v1.3: [lid, ci, x_mm, y_mm, z_mm, yaw_mdeg, gy_mm] (§3.6).

    Solo enteros: un float o un bool invalidan la fila.
    """
    if not isinstance(row, list) or len(row) != 7:
        return False
    lid, ci, x, y, z, yaw, gy = row
    if not valid_lid(lid):
        return False
    if not _is_int(ci) or ci < -1 or ci > _MAX_COUNT:
        return False
    if ci == -1:
        # Entidad que ya no vive o con lectura fuera de rango: ci=-1 y x,y,z,yaw a null (§3.3)
        if x is None and y is None and z is None and yaw is None:
            return gy is None or _valid_y_mm(gy)
        if x is None or y is None or z is None or yaw is None or gy is None:
            return False
    else:
        if x is None or y is None or z is None or yaw is None or gy is None:
            return False
    return (
        _valid_xz_mm(x, world_size)
        and _valid_y_mm(y)
        and _valid_xz_mm(z, world_size)
        and _valid_yaw_mdeg(yaw)
        and _valid_y_mm(gy)
    )


def valid_obs_now_row(row, world_size=_MAX_WORLD_SIZE):
    """Valida una fila de obs now v1.3: [lid, x_mm, y_mm, z_mm, yaw_mdeg, hp_milli, n_own, n_foreign].

    M15: una raiz muerta da `x`, `y`, `z`, `yaw` y `hp` a `None` y los dos
    contadores a 0. Se acepta esa variante exacta; cualquier combinacion con solo
    algunos nulos se rechaza. Solo enteros: un float o un bool invalidan la fila.
    """
    if not isinstance(row, list) or len(row) != 8:
        return False
    lid, x, y, z, yaw, hp, n_own, n_foreign = row
    if not valid_lid(lid):
        return False
    values = (x, y, z, yaw, hp)
    nulls = [val is None for val in values]
    if all(nulls):
        return _is_count(n_own) and _is_count(n_foreign) and n_own == 0 and n_foreign == 0
    if any(nulls):
        return False
    if not _valid_xz_mm(x, world_size):
        return False
    if not _valid_y_mm(y):
        return False
    if not _valid_xz_mm(z, world_size):
        return False
    if not _valid_yaw_mdeg(yaw):
        return False
    if not _valid_hp_milli(hp):
        return False
    if not _is_count(n_own) or not _is_count(n_foreign):
        return False
    return True


def valid_scene_read(read, require_obs=None, world_size=_MAX_WORLD_SIZE):
    """Valida la forma y los rangos normativos del read con scene (§3.2 y §3.6)."""
    if not isinstance(read, dict) or "generation" not in read:
        return False
    if not valid_world_read(read):
        return False
    if not _is_count(read.get("registry_n")):
        return False
    if not _is_num(world_size) or float(world_size) < 0 or float(world_size) > _MAX_WORLD_SIZE:
        return False

    gen = read.get("generation")
    if gen is not None:
        if not _is_rev(gen.get("rev")):
            return False
        if not isinstance(gen.get("plan_sha256"), str) or not _HEX64_RE.fullmatch(gen["plan_sha256"]):
            return False

    scene = read.get("scene")
    if not isinstance(scene, dict):
        return False
    if not valid_doc_id(scene.get("doc_id")):
        return False
    if not _is_count(scene.get("gen_n")):
        return False
    if not _is_count(scene.get("n")):
        return False
    retained_n = scene.get("retained_n")
    if not _is_count(retained_n):
        return False
    retained = scene.get("retained")
    if not isinstance(retained, list) or len(retained) > 8 or len(retained) > retained_n:
        return False
    if not all(valid_lid(lid) for lid in retained):
        return False

    if "pending" not in scene or "last" not in scene:
        return False
    pending = scene.get("pending")
    if pending is not None:
        if not isinstance(pending, dict):
            return False
        if not isinstance(pending.get("session"), str) or not _HEX16_RE.fullmatch(pending["session"]):
            return False
        if not isinstance(pending.get("op_id"), str) or not pending["op_id"]:
            return False
        if not _is_count(pending.get("n")):
            return False

    last = scene.get("last")
    if last is not None:
        if not isinstance(last, dict):
            return False
        if not isinstance(last.get("session"), str) or not _HEX16_RE.fullmatch(last["session"]):
            return False
        if not isinstance(last.get("op_id"), str) or not last["op_id"]:
            return False
        if last.get("verb") not in ("scene.apply", "scene.reset"):
            return False
        if last.get("outcome") not in ("done", "retained", "compensated", "interrupted"):
            return False

    if "obs" in read or require_obs is not None:
        obs = read.get("obs")
        if not isinstance(obs, dict):
            return False
        at = obs.get("at")
        if at not in ("checkpoint", "now"):
            return False
        if require_obs is not None and at != require_obs:
            return False
        rows = obs.get("rows")
        if not isinstance(rows, list):
            return False
        if at == "checkpoint":
            if not all(valid_obs_checkpoint_row(r, world_size) for r in rows):
                return False
        else:
            if not all(valid_obs_now_row(r, world_size) for r in rows):
                return False

    return True


# --- Predicados (§4.3), en mm ----------------------------------------------


def dist3(a, b):
    """Distancia euclidea 3D entre dos ternas (x, y, z)."""
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    dz = float(a[2]) - float(b[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def plan_matches_expectation(plan, expectation):
    """Comprueba que las columnas del plan casen con la expectativa de D11, en mm.

    Las columnas tienen que tener la misma longitud (una columna desalineada no casa).
    """
    if not isinstance(plan, dict) or not isinstance(expectation, dict):
        return False
    classes = plan.get("classes")
    cols = [plan.get(key) for key in PLAN_COLUMNS]
    if not isinstance(classes, list) or not all(isinstance(col, list) for col in cols):
        return False
    n = len(cols[0])
    if any(len(col) != n for col in cols):
        return False
    if n != len(expectation):
        return False
    seen = set()
    limit = POS_TOL - EPS_Q
    for lid, ci, x, z, yaw in zip(*cols):
        if not valid_lid(lid) or lid in seen or lid not in expectation:
            return False
        seen.add(lid)
        if not _is_int(ci) or ci < 0 or ci >= len(classes):
            return False
        exp_cls, exp_x, exp_z = expectation[lid]
        if classes[ci] != exp_cls:
            return False
        if not _valid_yaw_mdeg(yaw):
            return False
        if not _is_int(x) or not _is_int(z):
            return False
        if dist3((x, 0.0, z), (exp_x, 0.0, exp_z)) >= limit:
            return False
    return seen == set(expectation.keys())


def check_apply_predicate(order, read, expectation=None, world_size=_MAX_WORLD_SIZE):
    """Predicado de apply (§4.3), valido para la via directa y la reconciliacion. En mm."""
    if not isinstance(order, dict):
        return False
    exp = expectation if expectation is not None else order.get("expectation")
    if not isinstance(exp, dict):
        return False
    if not valid_scene_read(read, require_obs="checkpoint", world_size=world_size):
        return False
    if read.get("epoch") != order.get("epoch"):
        return False

    args = order.get("args") or {}
    if not plan_matches_expectation(args, exp):
        return False

    gen = read.get("generation")
    if not isinstance(gen, dict):
        return False
    if (
        gen.get("session") != order.get("session")
        or gen.get("op_id") != order.get("op_id")
        or gen.get("rev") != args.get("rev")
        or gen.get("hash") != args.get("hash")
        or gen.get("plan_sha256") != args.get("plan_sha256")
    ):
        return False

    scene = read["scene"]
    if scene.get("doc_id") != args.get("doc_id"):
        return False
    if scene.get("pending") is not None:
        return False
    if scene.get("n") != len(exp):
        return False
    if scene.get("retained_n") != 0 or scene.get("retained") != []:
        return False

    obs = read["obs"]
    if obs.get("at") != "checkpoint":
        return False
    rows = obs.get("rows")
    if not isinstance(rows, list) or len(rows) != len(exp):
        return False

    classes = args.get("classes") or []
    seen_lids = set()
    limit = POS_TOL - EPS_Q
    for row in rows:
        lid, ci, x, y, z, _yaw, gy = row
        if lid in seen_lids or lid not in exp:
            return False
        seen_lids.add(lid)
        if not _is_int(ci) or ci < 0 or ci >= len(classes):
            return False
        exp_cls, x_doc, z_doc = exp[lid]
        if classes[ci] != exp_cls:
            return False
        if x is None or y is None or z is None or gy is None:
            return False
        if dist3((x, y, z), (x_doc, gy, z_doc)) >= limit:
            return False

    return seen_lids == set(exp.keys())


def evaluate_reset_predicate(order, read, world_size=_MAX_WORLD_SIZE):
    """Predicado de reset (§4.3). Devuelve (state, reason)."""
    if not isinstance(order, dict) or not valid_scene_read(read, world_size=world_size):
        return ("fallido", "lectura_no_cumple")
    if read.get("epoch") != order.get("epoch"):
        return ("fallido", "lectura_no_cumple")
    scene = read["scene"]
    args = order.get("args") or {}
    if args.get("doc_id") and scene.get("doc_id") != args.get("doc_id"):
        return ("fallido", "lectura_no_cumple")
    last = scene.get("last")
    if not isinstance(last, dict):
        return ("fallido", "lectura_no_cumple")
    if (
        last.get("session") != order.get("session")
        or last.get("op_id") != order.get("op_id")
        or last.get("verb") != "scene.reset"
    ):
        return ("fallido", "lectura_no_cumple")

    outcome = last.get("outcome")
    n = scene.get("n")
    retained_n = scene.get("retained_n")
    retained = scene.get("retained")
    generation = read.get("generation")
    pending = scene.get("pending")

    if (
        outcome == "done"
        and n == 0
        and retained_n == 0
        and retained == []
        and generation is None
        and pending is None
    ):
        return ("observado", None)
    if (
        outcome == "retained"
        and n == retained_n
        and retained_n > 0
        and isinstance(retained, list)
        and len(retained) > 0
        and generation is None
        and pending is None
    ):
        return ("parcial", "contenido_ajeno")
    if outcome == "interrupted":
        return ("parcial", "interrumpida")
    return ("fallido", "lectura_no_cumple")


def evaluate_compensation_predicate(order, read, world_size=_MAX_WORLD_SIZE):
    """Predicado de «apply detenido» de un apply A (§4.3), sobre una lectura cuyo last es A
    con verb 'scene.apply', `generation == null` y `scene.pending` distinto de A.

    Devuelve:
    - ('parcial', 'compensada') si outcome == 'compensated' y scene.n == 0;
    - ('parcial', 'contenido_ajeno') si outcome == 'retained', retained no vacio y
      n >= retained_n >= 1;
    - ('parcial', 'interrumpida') si outcome == 'interrupted';
    - ('unresolved', None) si scene.pending sigue siendo A (toca compensar, §4.5);
    - ('fallido', 'lectura_no_cumple') en cualquier otro caso, incluida una generation no nula.
    """
    if not isinstance(order, dict) or not valid_scene_read(read, world_size=world_size):
        return ("fallido", "lectura_no_cumple")
    if read.get("epoch") != order.get("epoch"):
        return ("fallido", "lectura_no_cumple")
    scene = read["scene"]
    args = order.get("args") or {}
    if args.get("doc_id") and scene.get("doc_id") != args.get("doc_id"):
        return ("fallido", "lectura_no_cumple")
    last = scene.get("last")
    if not isinstance(last, dict):
        return ("fallido", "lectura_no_cumple")
    if (
        last.get("session") != order.get("session")
        or last.get("op_id") != order.get("op_id")
        or last.get("verb") != "scene.apply"
    ):
        return ("fallido", "lectura_no_cumple")

    pending = scene.get("pending")
    pending_is_a = (
        isinstance(pending, dict)
        and pending.get("session") == order.get("session")
        and pending.get("op_id") == order.get("op_id")
    )
    if pending_is_a:
        return ("unresolved", None)

    generation = read.get("generation")
    if generation is not None:
        return ("fallido", "lectura_no_cumple")

    outcome = last.get("outcome")
    n = scene.get("n")
    retained_n = scene.get("retained_n")
    retained = scene.get("retained")

    if outcome == "compensated" and n == 0:
        return ("parcial", "compensada")
    if (
        outcome == "retained"
        and isinstance(retained, list)
        and len(retained) > 0
        and _is_int(retained_n)
        and retained_n >= 1
        and _is_int(n)
        and n >= retained_n
    ):
        return ("parcial", "contenido_ajeno")
    if outcome == "interrupted":
        return ("parcial", "interrumpida")
    return ("fallido", "lectura_no_cumple")
