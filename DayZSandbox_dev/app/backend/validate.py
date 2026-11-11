from __future__ import annotations

import datetime
import math
import re

SCHEMA_VERSION = "dsbx.scene/1"
MAP_SIZE = 15360.0
KINDS = ("actor", "objeto", "infectado", "animal")
KIND_PREFIX = {
    "actor": "act",
    "objeto": "obj",
    "infectado": "zmb",
    "animal": "ani",
}
NEXT_KEYS = ("act", "obj", "zmb", "ani", "cam")
BEHAVIOURS = ("HOLD", "ONCE", "LOOP", "ROAM")
DEFAULT_WARDROBES = ("partisano", "civil", "medica", "cazador")
DEFAULT_EMOTES = (
    "EmoteGreeting",
    "EmotePoint",
    "EmoteThumb",
    "EmoteSurrender",
    "EmoteSalute",
    "EmoteFacepalm",
    "EmoteTaunt",
    "EmoteHeart",
)

ROOT_FIELDS = ("schema", "doc_id", "name", "map", "ambiente", "entities", "cameras", "next")
AMBIENTE_FIELDS = ("fecha", "hora", "nubes", "niebla", "lluvia", "viento")
BASE_ENTITY_FIELDS = ("id", "kind", "cls", "name", "x", "z", "yaw")
ACTOR_EXTRA_FIELDS = ("wardrobe", "behaviour", "roam", "marks", "gestures")
ACTOR_FIELDS = BASE_ENTITY_FIELDS + ACTOR_EXTRA_FIELDS
MARK_FIELDS = ("x", "z")
GESTURE_FIELDS = ("emote", "at", "t")
CAMERA_FIELDS = ("id", "name", "keys")
CAMERA_KEY_FIELDS = ("t", "x", "y", "z", "yaw", "pitch", "fov", "focus")

_HORA_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID_NUM_RE = re.compile(r"^(0[1-9]|[1-9]\d+)$")


def _esc(token: str | int) -> str:
    s = str(token)
    return s.replace("~", "~0").replace("/", "~1")


def _ptr(*parts: str | int) -> str:
    if not parts:
        return ""
    return "/" + "/".join(_esc(p) for p in parts)


def _err(code: str, pointer: str, msg: str) -> dict:
    return {"code": code, "pointer": pointer, "msg": msg}


def _is_num(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _is_int(val: object) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _extract_names(items: object, *, check_cert: bool = False) -> set[str]:
    out: set[str] = set()
    if not isinstance(items, (list, tuple, set)):
        return out
    for it in items:
        if isinstance(it, str):
            out.add(it)
        elif isinstance(it, (list, tuple)) and it and isinstance(it[0], str):
            out.add(it[0])
        elif isinstance(it, dict):
            if check_cert and "cert" in it and not it["cert"]:
                continue
            name = it.get("cls") if isinstance(it.get("cls"), str) else it.get("id")
            if isinstance(name, str):
                out.add(name)
    return out


def _valid_entity_id(val: str, expected_prefix: str | None) -> bool:
    if "-" not in val:
        return False
    prefix, num = val.split("-", 1)
    if expected_prefix is not None:
        if prefix != expected_prefix:
            return False
    elif prefix not in ("act", "obj", "zmb", "ani"):
        return False
    return bool(_ID_NUM_RE.match(num))


def _valid_cam_id(val: str) -> bool:
    if not val.startswith("cam-"):
        return False
    return bool(_ID_NUM_RE.match(val[4:]))


def _validate_coord(val: object, pointer: str, label: str, errors: list[dict]) -> None:
    if not _is_num(val):
        errors.append(_err("bad_type", pointer, f"{label} debe ser numérico."))
        return
    fval = float(val)
    if not math.isfinite(fval):
        errors.append(_err("bad_value", pointer, f"{label} debe ser finito."))
        return
    if fval < 0.0 or fval > MAP_SIZE:
        errors.append(_err("out_of_map", pointer, f"{label} fuera del mapa [0, 15360]."))


def validate(doc: dict, catalog: dict) -> list[dict]:
    errors: list[dict] = []
    if not isinstance(doc, dict):
        return [_err("bad_type", "", "El documento debe ser un objeto JSON.")]

    cat = catalog if isinstance(catalog, dict) else {}
    raw_classes = cat.get("classes") if isinstance(cat.get("classes"), dict) else {}
    classes_by_kind: dict[str, set[str]] = {
        k: _extract_names(raw_classes.get(k, ())) for k in KINDS
    }
    raw_caps = cat.get("caps") if isinstance(cat.get("caps"), dict) else {}
    wardrobes = (
        _extract_names(cat["wardrobes"])
        if "wardrobes" in cat and cat["wardrobes"] is not None
        else set(DEFAULT_WARDROBES)
    )
    emotes = (
        _extract_names(cat["emotes"], check_cert=True)
        if "emotes" in cat and cat["emotes"] is not None
        else set(DEFAULT_EMOTES)
    )

    for k in doc:
        if k not in ROOT_FIELDS:
            errors.append(_err("unknown_field", _ptr(k), f"Campo desconocido '{k}'."))

    for req in ROOT_FIELDS:
        if req not in doc:
            errors.append(_err("missing_field", _ptr(req), f"Falta el campo obligatorio '{req}'."))

    if "schema" in doc:
        if doc["schema"] != SCHEMA_VERSION:
            errors.append(
                _err("unsupported_version", _ptr("schema"), "Versión de esquema no soportada.")
            )

    if "doc_id" in doc:
        if not isinstance(doc["doc_id"], str):
            errors.append(_err("bad_type", _ptr("doc_id"), "doc_id debe ser una cadena."))
        elif not doc["doc_id"].strip():
            errors.append(_err("bad_value", _ptr("doc_id"), "doc_id no puede estar vacío."))

    if "name" in doc:
        if not isinstance(doc["name"], str):
            errors.append(_err("bad_type", _ptr("name"), "name debe ser una cadena."))
        elif not doc["name"].strip():
            errors.append(_err("bad_value", _ptr("name"), "name no puede estar vacío."))

    if "map" in doc:
        if not isinstance(doc["map"], str):
            errors.append(_err("bad_type", _ptr("map"), "map debe ser una cadena."))
        elif doc["map"] != "chernarusplus":
            errors.append(_err("bad_value", _ptr("map"), "Mapa no soportado en M1."))

    if "ambiente" in doc:
        amb = doc["ambiente"]
        if not isinstance(amb, dict):
            errors.append(_err("bad_type", _ptr("ambiente"), "ambiente debe ser un objeto."))
        else:
            for k in amb:
                if k not in AMBIENTE_FIELDS:
                    errors.append(
                        _err("unknown_field", _ptr("ambiente", k), f"Campo desconocido '{k}'.")
                    )
            for req in AMBIENTE_FIELDS:
                if req not in amb:
                    errors.append(
                        _err(
                            "missing_field",
                            _ptr("ambiente", req),
                            f"Falta el campo '{req}' en ambiente.",
                        )
                    )
            if "fecha" in amb:
                fecha = amb["fecha"]
                if not isinstance(fecha, str):
                    errors.append(
                        _err("bad_type", _ptr("ambiente", "fecha"), "fecha debe ser una cadena.")
                    )
                elif not _FECHA_RE.match(fecha):
                    errors.append(
                        _err("bad_value", _ptr("ambiente", "fecha"), "fecha debe ser YYYY-MM-DD.")
                    )
                else:
                    try:
                        datetime.date.fromisoformat(fecha)
                    except ValueError:
                        errors.append(
                            _err("bad_value", _ptr("ambiente", "fecha"), "Fecha inválida.")
                        )
            if "hora" in amb:
                hora = amb["hora"]
                if not isinstance(hora, str):
                    errors.append(
                        _err("bad_type", _ptr("ambiente", "hora"), "hora debe ser una cadena.")
                    )
                elif not _HORA_RE.match(hora):
                    errors.append(
                        _err("bad_value", _ptr("ambiente", "hora"), "hora debe tener formato HH:MM.")
                    )
            for weather_key in ("nubes", "niebla", "lluvia"):
                if weather_key in amb:
                    v = amb[weather_key]
                    p = _ptr("ambiente", weather_key)
                    if not _is_num(v):
                        errors.append(_err("bad_type", p, f"{weather_key} debe ser numérico."))
                    elif not math.isfinite(float(v)) or float(v) < 0.0 or float(v) > 1.0:
                        errors.append(
                            _err("bad_value", p, f"{weather_key} debe estar en [0, 1].")
                        )
            if "viento" in amb:
                v = amb["viento"]
                p = _ptr("ambiente", "viento")
                if not _is_num(v):
                    errors.append(_err("bad_type", p, "viento debe ser numérico."))
                elif not math.isfinite(float(v)) or float(v) < 0.0 or float(v) > 20.0:
                    errors.append(_err("bad_value", p, "viento debe estar en [0, 20]."))

    if "entities" in doc:
        ents = doc["entities"]
        if not isinstance(ents, list):
            errors.append(_err("bad_type", _ptr("entities"), "entities debe ser una lista."))
        else:
            seen_ids: set[str] = set()
            counts: dict[str, int] = {k: 0 for k in KINDS}
            for i, ent in enumerate(ents):
                ep = _ptr("entities", i)
                if not isinstance(ent, dict):
                    errors.append(_err("bad_type", ep, "Cada entidad debe ser un objeto."))
                    continue

                kind = ent.get("kind")
                valid_kind = isinstance(kind, str) and kind in KINDS
                if valid_kind:
                    counts[kind] += 1

                if kind == "actor":
                    allowed = ACTOR_FIELDS
                    required = ACTOR_FIELDS
                elif valid_kind:
                    allowed = BASE_ENTITY_FIELDS
                    required = BASE_ENTITY_FIELDS
                else:
                    allowed = ACTOR_FIELDS
                    required = BASE_ENTITY_FIELDS

                for k in ent:
                    if k not in allowed:
                        errors.append(
                            _err("unknown_field", _ptr("entities", i, k), f"Campo desconocido '{k}'.")
                        )

                for req in required:
                    if req not in ent:
                        errors.append(
                            _err(
                                "missing_field",
                                _ptr("entities", i, req),
                                f"Falta el campo '{req}'.",
                            )
                        )

                if "kind" in ent:
                    if not isinstance(kind, str):
                        errors.append(
                            _err("bad_type", _ptr("entities", i, "kind"), "kind debe ser una cadena.")
                        )
                    elif not valid_kind:
                        errors.append(
                            _err("bad_value", _ptr("entities", i, "kind"), "kind inválido.")
                        )

                if "id" in ent:
                    eid = ent["id"]
                    idp = _ptr("entities", i, "id")
                    if not isinstance(eid, str):
                        errors.append(_err("bad_type", idp, "id debe ser una cadena."))
                    else:
                        exp_prefix = KIND_PREFIX.get(kind) if valid_kind else None
                        if not _valid_entity_id(eid, exp_prefix) or eid in seen_ids:
                            errors.append(_err("bad_id", idp, f"id inválido o repetido: '{eid}'."))
                        seen_ids.add(eid)

                if "cls" in ent:
                    cls_val = ent["cls"]
                    clsp = _ptr("entities", i, "cls")
                    if not isinstance(cls_val, str):
                        errors.append(_err("bad_type", clsp, "cls debe ser una cadena."))
                    elif valid_kind and cls_val not in classes_by_kind.get(kind, set()):
                        errors.append(
                            _err(
                                "unknown_class",
                                clsp,
                                f"La clase '{cls_val}' no está en el catálogo para '{kind}'.",
                            )
                        )

                if "name" in ent:
                    nm = ent["name"]
                    nmp = _ptr("entities", i, "name")
                    if not isinstance(nm, str):
                        errors.append(_err("bad_type", nmp, "name debe ser una cadena."))
                    elif not nm.strip():
                        errors.append(_err("bad_value", nmp, "name no puede estar vacío."))

                if "x" in ent:
                    _validate_coord(ent["x"], _ptr("entities", i, "x"), "x", errors)
                if "z" in ent:
                    _validate_coord(ent["z"], _ptr("entities", i, "z"), "z", errors)

                if "yaw" in ent:
                    yaw = ent["yaw"]
                    yawp = _ptr("entities", i, "yaw")
                    if not _is_num(yaw):
                        errors.append(_err("bad_type", yawp, "yaw debe ser numérico."))
                    elif not math.isfinite(float(yaw)) or float(yaw) < 0.0 or float(yaw) >= 360.0:
                        errors.append(_err("bad_value", yawp, "yaw debe estar en [0, 360)."))

                if kind == "actor":
                    if "wardrobe" in ent:
                        w = ent["wardrobe"]
                        wp = _ptr("entities", i, "wardrobe")
                        if not isinstance(w, str):
                            errors.append(_err("bad_type", wp, "wardrobe debe ser una cadena."))
                        elif w not in wardrobes:
                            errors.append(_err("bad_value", wp, f"Vestuario desconocido '{w}'."))

                    if "behaviour" in ent:
                        b = ent["behaviour"]
                        bp = _ptr("entities", i, "behaviour")
                        if not isinstance(b, str):
                            errors.append(_err("bad_type", bp, "behaviour debe ser una cadena."))
                        elif b not in BEHAVIOURS:
                            errors.append(_err("bad_value", bp, f"Comportamiento inválido '{b}'."))

                    if "roam" in ent:
                        r = ent["roam"]
                        rp = _ptr("entities", i, "roam")
                        if not _is_num(r):
                            errors.append(_err("bad_type", rp, "roam debe ser numérico."))
                        elif not math.isfinite(float(r)) or float(r) <= 0.0:
                            errors.append(_err("bad_value", rp, "roam debe ser positivo."))

                    marks_list: list | None = None
                    if "marks" in ent:
                        marks = ent["marks"]
                        mp = _ptr("entities", i, "marks")
                        if not isinstance(marks, list):
                            errors.append(_err("bad_type", mp, "marks debe ser una lista."))
                        else:
                            marks_list = marks
                            for mi, m in enumerate(marks):
                                mip = _ptr("entities", i, "marks", mi)
                                if not isinstance(m, dict):
                                    errors.append(
                                        _err("bad_type", mip, "Cada marca debe ser un objeto.")
                                    )
                                    continue
                                for mk in m:
                                    if mk not in MARK_FIELDS:
                                        errors.append(
                                            _err(
                                                "unknown_field",
                                                _ptr("entities", i, "marks", mi, mk),
                                                f"Campo desconocido '{mk}'.",
                                            )
                                        )
                                for req in MARK_FIELDS:
                                    if req not in m:
                                        errors.append(
                                            _err(
                                                "missing_field",
                                                _ptr("entities", i, "marks", mi, req),
                                                f"Falta '{req}' en la marca.",
                                            )
                                        )
                                if "x" in m:
                                    _validate_coord(
                                        m["x"], _ptr("entities", i, "marks", mi, "x"), "x", errors
                                    )
                                if "z" in m:
                                    _validate_coord(
                                        m["z"], _ptr("entities", i, "marks", mi, "z"), "z", errors
                                    )

                    if "gestures" in ent:
                        gestures = ent["gestures"]
                        gp = _ptr("entities", i, "gestures")
                        if not isinstance(gestures, list):
                            errors.append(_err("bad_type", gp, "gestures debe ser una lista."))
                        else:
                            num_marks = len(marks_list) if marks_list is not None else 0
                            for gi, g in enumerate(gestures):
                                gip = _ptr("entities", i, "gestures", gi)
                                if not isinstance(g, dict):
                                    errors.append(
                                        _err("bad_type", gip, "Cada gesto debe ser un objeto.")
                                    )
                                    continue
                                for gk in g:
                                    if gk not in GESTURE_FIELDS:
                                        errors.append(
                                            _err(
                                                "unknown_field",
                                                _ptr("entities", i, "gestures", gi, gk),
                                                f"Campo desconocido '{gk}'.",
                                            )
                                        )
                                if "emote" not in g:
                                    errors.append(
                                        _err(
                                            "missing_field",
                                            _ptr("entities", i, "gestures", gi, "emote"),
                                            "Falta 'emote' en el gesto.",
                                        )
                                    )
                                else:
                                    em = g["emote"]
                                    emp = _ptr("entities", i, "gestures", gi, "emote")
                                    if not isinstance(em, str):
                                        errors.append(
                                            _err("bad_type", emp, "emote debe ser una cadena.")
                                        )
                                    elif em not in emotes:
                                        errors.append(
                                            _err("bad_value", emp, f"Gesto inválido '{em}'.")
                                        )

                                has_at = "at" in g
                                has_t = "t" in g
                                if not has_at and not has_t:
                                    errors.append(
                                        _err(
                                            "missing_field",
                                            gip,
                                            "El gesto requiere 'at' o 't'.",
                                        )
                                    )
                                elif has_at and has_t:
                                    errors.append(
                                        _err(
                                            "bad_value",
                                            gip,
                                            "El gesto debe llevar exactamente uno de 'at' o 't'.",
                                        )
                                    )
                                elif has_at:
                                    at_val = g["at"]
                                    atp = _ptr("entities", i, "gestures", gi, "at")
                                    if not _is_int(at_val):
                                        errors.append(
                                            _err("bad_type", atp, "at debe ser un entero.")
                                        )
                                    elif at_val < 1:
                                        errors.append(
                                            _err("bad_value", atp, "at debe ser >= 1.")
                                        )
                                    elif marks_list is not None and at_val > num_marks:
                                        errors.append(
                                            _err(
                                                "bad_ref",
                                                atp,
                                                f"El gesto referencia la marca {at_val}, pero hay {num_marks}.",
                                            )
                                        )
                                elif has_t:
                                    t_val = g["t"]
                                    tp = _ptr("entities", i, "gestures", gi, "t")
                                    if not _is_num(t_val):
                                        errors.append(
                                            _err("bad_type", tp, "t debe ser numérico.")
                                        )
                                    elif not math.isfinite(float(t_val)) or float(t_val) < 0.0:
                                        errors.append(
                                            _err("bad_value", tp, "t debe ser >= 0.")
                                        )

            for k in KINDS:
                cap = raw_caps.get(k)
                if _is_int(cap) and counts[k] > cap:
                    errors.append(
                        _err(
                            "budget_exceeded",
                            _ptr("entities"),
                            f"Tope de '{k}' superado ({counts[k]} > {cap}).",
                        )
                    )

    if "cameras" in doc:
        cams = doc["cameras"]
        if not isinstance(cams, list):
            errors.append(_err("bad_type", _ptr("cameras"), "cameras debe ser una lista."))
        else:
            seen_cam_ids: set[str] = set()
            for i, cam in enumerate(cams):
                cp = _ptr("cameras", i)
                if not isinstance(cam, dict):
                    errors.append(_err("bad_type", cp, "Cada cámara debe ser un objeto."))
                    continue
                for ck in cam:
                    if ck not in CAMERA_FIELDS:
                        errors.append(
                            _err(
                                "unknown_field",
                                _ptr("cameras", i, ck),
                                f"Campo desconocido '{ck}'.",
                            )
                        )
                for req in CAMERA_FIELDS:
                    if req not in cam:
                        errors.append(
                            _err(
                                "missing_field",
                                _ptr("cameras", i, req),
                                f"Falta el campo '{req}' en cámara.",
                            )
                        )
                if "id" in cam:
                    cid = cam["id"]
                    cidp = _ptr("cameras", i, "id")
                    if not isinstance(cid, str):
                        errors.append(_err("bad_type", cidp, "id de cámara debe ser una cadena."))
                    else:
                        if not _valid_cam_id(cid) or cid in seen_cam_ids:
                            errors.append(
                                _err("bad_id", cidp, f"id de cámara inválido o repetido: '{cid}'.")
                            )
                        seen_cam_ids.add(cid)
                if "name" in cam:
                    cnm = cam["name"]
                    cnmp = _ptr("cameras", i, "name")
                    if not isinstance(cnm, str):
                        errors.append(
                            _err("bad_type", cnmp, "name de cámara debe ser una cadena.")
                        )
                    elif not cnm.strip():
                        errors.append(
                            _err("bad_value", cnmp, "name de cámara no puede estar vacío.")
                        )
                if "keys" in cam:
                    keys = cam["keys"]
                    kp = _ptr("cameras", i, "keys")
                    if not isinstance(keys, list):
                        errors.append(_err("bad_type", kp, "keys debe ser una lista."))
                    elif len(keys) == 0:
                        errors.append(
                            _err("bad_value", kp, "La cámara debe tener al menos una clave.")
                        )
                    else:
                        prev_t: float | None = None
                        for ki, key in enumerate(keys):
                            kip = _ptr("cameras", i, "keys", ki)
                            if not isinstance(key, dict):
                                errors.append(
                                    _err("bad_type", kip, "Cada clave debe ser un objeto.")
                                )
                                continue
                            for kk in key:
                                if kk not in CAMERA_KEY_FIELDS:
                                    errors.append(
                                        _err(
                                            "unknown_field",
                                            _ptr("cameras", i, "keys", ki, kk),
                                            f"Campo desconocido '{kk}'.",
                                        )
                                    )
                            for req in CAMERA_KEY_FIELDS:
                                if req not in key:
                                    errors.append(
                                        _err(
                                            "missing_field",
                                            _ptr("cameras", i, "keys", ki, req),
                                            f"Falta '{req}' en la clave de cámara.",
                                        )
                                    )
                            if "t" in key:
                                tv = key["t"]
                                tp = _ptr("cameras", i, "keys", ki, "t")
                                if not _is_num(tv):
                                    errors.append(_err("bad_type", tp, "t debe ser numérico."))
                                elif not math.isfinite(float(tv)):
                                    errors.append(_err("bad_value", tp, "t debe ser finito."))
                                else:
                                    ft = float(tv)
                                    if ki == 0:
                                        if ft != 0.0:
                                            errors.append(
                                                _err(
                                                    "bad_order",
                                                    tp,
                                                    "La primera clave de cámara debe tener t = 0.",
                                                )
                                            )
                                    elif prev_t is not None and ft <= prev_t:
                                        errors.append(
                                            _err(
                                                "bad_order",
                                                tp,
                                                "Las claves de cámara deben tener t estrictamente creciente.",
                                            )
                                        )
                                    prev_t = ft

                            if "x" in key:
                                _validate_coord(
                                    key["x"], _ptr("cameras", i, "keys", ki, "x"), "x", errors
                                )
                            if "z" in key:
                                _validate_coord(
                                    key["z"], _ptr("cameras", i, "keys", ki, "z"), "z", errors
                                )
                            if "y" in key:
                                yv = key["y"]
                                yp = _ptr("cameras", i, "keys", ki, "y")
                                if not _is_num(yv):
                                    errors.append(_err("bad_type", yp, "y debe ser numérico."))
                                elif not math.isfinite(float(yv)):
                                    errors.append(_err("bad_value", yp, "y debe ser finito."))

                            if "yaw" in key:
                                yw = key["yaw"]
                                ywp = _ptr("cameras", i, "keys", ki, "yaw")
                                if not _is_num(yw):
                                    errors.append(_err("bad_type", ywp, "yaw debe ser numérico."))
                                elif (
                                    not math.isfinite(float(yw))
                                    or float(yw) < -180.0
                                    or float(yw) >= 360.0
                                ):
                                    errors.append(_err("bad_value", ywp, "yaw de cámara inválido."))

                            if "pitch" in key:
                                pt = key["pitch"]
                                ptp = _ptr("cameras", i, "keys", ki, "pitch")
                                if not _is_num(pt):
                                    errors.append(
                                        _err("bad_type", ptp, "pitch debe ser numérico.")
                                    )
                                elif (
                                    not math.isfinite(float(pt))
                                    or float(pt) < -90.0
                                    or float(pt) > 90.0
                                ):
                                    errors.append(
                                        _err("bad_value", ptp, "pitch debe estar en [-90, 90].")
                                    )

                            if "fov" in key:
                                fv = key["fov"]
                                fvp = _ptr("cameras", i, "keys", ki, "fov")
                                if not _is_num(fv):
                                    errors.append(_err("bad_type", fvp, "fov debe ser numérico."))
                                elif (
                                    not math.isfinite(float(fv))
                                    or float(fv) <= 0.0
                                    or float(fv) >= 180.0
                                ):
                                    errors.append(
                                        _err("bad_value", fvp, "fov debe estar en (0, 180).")
                                    )

                            if "focus" in key:
                                fc = key["focus"]
                                fcp = _ptr("cameras", i, "keys", ki, "focus")
                                if not _is_num(fc):
                                    errors.append(
                                        _err("bad_type", fcp, "focus debe ser numérico.")
                                    )
                                elif not math.isfinite(float(fc)) or float(fc) <= 0.0:
                                    errors.append(_err("bad_value", fcp, "focus debe ser > 0."))

    if "next" in doc:
        nxt = doc["next"]
        if not isinstance(nxt, dict):
            errors.append(_err("bad_type", _ptr("next"), "next debe ser un objeto."))
        else:
            for nk in nxt:
                if nk not in NEXT_KEYS:
                    errors.append(
                        _err("unknown_field", _ptr("next", nk), f"Campo desconocido '{nk}'.")
                    )
            for req in NEXT_KEYS:
                if req not in nxt:
                    errors.append(
                        _err("missing_field", _ptr("next", req), f"Falta '{req}' en next.")
                    )
                else:
                    nv = nxt[req]
                    np = _ptr("next", req)
                    if not _is_int(nv):
                        errors.append(_err("bad_type", np, f"next.{req} debe ser un entero."))
                    elif nv < 1:
                        errors.append(_err("bad_value", np, f"next.{req} debe ser >= 1."))

    return errors
