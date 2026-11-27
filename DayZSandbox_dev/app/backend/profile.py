"""Perfil local del estudio, lectura del esquema y vista del catálogo (brief F6-web-1 §2)."""
import json
import os
import re
import tempfile
import threading
import time

from app.backend.validate import (
    DEFAULT_EMOTES,
    DEFAULT_WARDROBES,
    KINDS,
    _esc,
    _extract_names,
    _is_int,
)

MAX_PROFILE_BYTES = 65536
MAX_KEYMAP_ENTRIES = 64
_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_LOCK = threading.Lock()

# En Windows, os.replace falla con PermissionError (WinError 5) si otro tiene el perfil abierto en
# ese instante: un antivirus, un indexador o cualquier lector. Es pasajero, así que se reintenta un
# rato corto; cualquier otro OSError (disco lleno) falla a la primera.
REPLACE_RETRIES = 10
REPLACE_WAIT_S = 0.05


def _replace_with_retry(src, dst):
    for attempt in range(REPLACE_RETRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES - 1:
                raise
            time.sleep(REPLACE_WAIT_S)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_SCHEMA = os.path.join(_ROOT, "schemas", "scene.schema.json")


def _fail(code, msg, pointer=""):
    return {"ok": False, "code": code, "pointer": pointer, "msg": msg}


def _same_path(a, b):
    na = os.path.normcase(os.path.abspath(os.path.realpath(a)))
    nb = os.path.normcase(os.path.abspath(os.path.realpath(b)))
    if na == nb:
        return True
    if os.path.exists(a) and os.path.exists(b):
        try:
            return os.path.samefile(a, b)
        except OSError:
            return False
    return False


def _has_control_char(s):
    for ch in s:
        code = ord(ch)
        if code < 32 or 127 <= code <= 159:
            return True
    return False


def validate_profile(body):
    """Devuelve None si el perfil cumple §2.2, o el dict de error 400 bad_profile."""
    if not isinstance(body, dict):
        return _fail("bad_profile", "El perfil tiene que ser un objeto JSON", "")
    expected_root = ("v", "layouts", "keymap")
    for k in body:
        if k not in expected_root:
            return _fail("bad_profile", "Clave desconocida en el perfil: " + str(k), "/" + _esc(str(k)))
    for k in expected_root:
        if k not in body:
            return _fail("bad_profile", "Falta la clave obligatoria: " + k, "/" + k)

    v = body["v"]
    if isinstance(v, bool) or not isinstance(v, int) or v != 1:
        return _fail("bad_profile", "v tiene que ser el entero 1", "/v")

    layouts = body["layouts"]
    if not isinstance(layouts, dict):
        return _fail("bad_profile", "layouts tiene que ser un objeto", "/layouts")
    expected_layouts = ("escena", "rodaje")
    for k in layouts:
        if k not in expected_layouts:
            return _fail(
                "bad_profile",
                "Modo desconocido en layouts: " + str(k),
                "/layouts/" + _esc(str(k)),
            )
    for k in expected_layouts:
        if k not in layouts:
            return _fail("bad_profile", "Falta el modo en layouts: " + k, "/layouts/" + k)
        val = layouts[k]
        if val is not None and not isinstance(val, dict):
            return _fail(
                "bad_profile",
                "El layout de " + k + " tiene que ser un objeto o null",
                "/layouts/" + k,
            )

    keymap = body["keymap"]
    if not isinstance(keymap, dict) or len(keymap) > MAX_KEYMAP_ENTRIES:
        return _fail("bad_profile", "keymap tiene que ser un objeto de hasta 64 entradas", "/keymap")
    for k, val in keymap.items():
        ptr = "/keymap/" + _esc(str(k))
        if not isinstance(k, str) or not _KEY_RE.fullmatch(k):
            return _fail("bad_profile", "Identificador de acción no válido: " + str(k), ptr)
        if val is None:
            continue
        if not isinstance(val, str) or not (1 <= len(val) <= 40) or _has_control_char(val):
            return _fail("bad_profile", "Atajo no válido para " + k, ptr)

    return None


class Profile:
    """Gestiona la lectura del esquema, la vista del catálogo y el fichero profile.json."""

    def __init__(self, store, profile_path=None, schema_path=None):
        self.store = store
        scene_abs = os.path.abspath(store.path)
        if profile_path is None:
            resolved_profile = os.path.join(os.path.dirname(scene_abs), "profile.json")
        else:
            resolved_profile = os.path.abspath(profile_path)
        if _same_path(resolved_profile, scene_abs):
            raise ValueError("La ruta del perfil no puede ser el mismo fichero que la escena")
        self.path = resolved_profile
        self.schema_path = os.path.abspath(schema_path) if schema_path is not None else _DEFAULT_SCHEMA
        self._schema = self._load_schema()

    def _load_schema(self):
        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    def get_schema(self):
        if self._schema is None:
            return 503, _fail("schema_unavailable", "El esquema no está disponible")
        return 200, self._schema

    def get_catalog(self):
        cat = self.store.catalog if isinstance(self.store.catalog, dict) else {}
        raw_classes = cat.get("classes") if isinstance(cat.get("classes"), dict) else {}
        classes = {
            k: sorted(_extract_names(raw_classes.get(k, ())))
            for k in KINDS
        }
        raw_caps = cat.get("caps") if isinstance(cat.get("caps"), dict) else {}
        caps = {
            k: raw_caps[k]
            for k in KINDS
            if _is_int(raw_caps.get(k))
        }
        wardrobes = (
            sorted(_extract_names(cat["wardrobes"]))
            if "wardrobes" in cat and cat["wardrobes"] is not None
            else sorted(DEFAULT_WARDROBES)
        )
        emotes = (
            sorted(_extract_names(cat["emotes"], check_cert=True))
            if "emotes" in cat and cat["emotes"] is not None
            else sorted(DEFAULT_EMOTES)
        )
        raw_wi = cat.get("wardrobe_items")
        wardrobe_items = {}
        for name in wardrobes:
            src = raw_wi.get(name) if isinstance(raw_wi, dict) else None
            if not isinstance(src, (list, tuple)):
                wardrobe_items[name] = []
            else:
                wardrobe_items[name] = [x for x in src if isinstance(x, str) and x]
        return {
            "ok": True,
            "source": "fixture",
            "classes": classes,
            "caps": caps,
            "wardrobes": wardrobes,
            "emotes": emotes,
            "wardrobe_items": wardrobe_items,
        }

    def get_profile(self):
        with _LOCK:
            if not os.path.exists(self.path):
                return {"ok": True, "profile": None, "corrupt": False}
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, UnicodeError, ValueError):
                return {"ok": True, "profile": None, "corrupt": True}
            if not isinstance(data, dict) or validate_profile(data) is not None:
                return {"ok": True, "profile": None, "corrupt": True}
            return {"ok": True, "profile": data, "corrupt": False}

    def save_profile(self, body, content_length):
        if content_length > MAX_PROFILE_BYTES:
            return 413, _fail("profile_too_large", "El perfil supera 65536 bytes")
        err = validate_profile(body)
        if err is not None:
            return 400, err
        with _LOCK:
            directory = os.path.dirname(self.path) or "."
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix="profile-", suffix=".tmp", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(body, f, ensure_ascii=False)
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                _replace_with_retry(tmp, self.path)
                tmp = None
            finally:
                if tmp is not None and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
        return 200, {"ok": True}
