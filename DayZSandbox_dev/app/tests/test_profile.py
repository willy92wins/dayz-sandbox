"""Pruebas del esquema, catálogo y perfil local (brief F6-web-1 §8.1, T1-T10)."""
import copy
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import app.backend.profile as profile_mod
from app.backend.server import Backend
from app.backend.store import Store
from app.backend.validate import DEFAULT_EMOTES, DEFAULT_WARDROBES, KINDS, _extract_names

from .test_server import AK, FIXTURES, HK, ROOT, Base, Env
from .test_server_web import cookie_header, good_origin, login, raw


def valid_profile(keymap=None, escena=None, rodaje=None):
    return {
        "v": 1,
        "layouts": {
            "escena": {} if escena is None else escena,
            "rodaje": rodaje,
        },
        "keymap": {"aplicar": "Ctrl+Enter"} if keymap is None else keymap,
    }


def make_sized_profile(target_bytes):
    base = {
        "v": 1,
        "layouts": {"escena": {"pad": ""}, "rodaje": None},
        "keymap": {"aplicar": "Ctrl+Enter"},
    }
    empty_raw = json.dumps(base, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    pad_len = target_bytes - len(empty_raw)
    assert pad_len >= 0, pad_len
    base["layouts"]["escena"]["pad"] = "a" * pad_len
    raw_bytes = json.dumps(base, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(raw_bytes) == target_bytes, (len(raw_bytes), target_bytes)
    return base, raw_bytes


class ProfileBase(Base):
    def do_login(self, key=HK, headers=None):
        return login(self.env, key=key, headers=headers)

    def cookie_hdrs(self, sid, csrf, origin=True):
        h = {"Cookie": cookie_header(self.env, sid)}
        if origin is True:
            h["Origin"] = good_origin(self.env)
        elif isinstance(origin, str):
            h["Origin"] = origin
        if csrf is not None:
            h["X-CSRF-Token"] = csrf
        return h

    @property
    def profile_path(self):
        return Path(self.env.backend.profile.path)


class T1Catalogo(ProfileBase):
    def test_catalogo_con_cookie_y_bearer_ia_normalizado_y_ordenado(self):
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            cat_fixture = json.load(f)
        _, _, _, sid, _ = self.do_login()
        st_c, _, _, body_c = raw(
            self.env, "GET", "/api/catalog", headers={"Cookie": cookie_header(self.env, sid)}
        )
        st_ai, body_ai = self.env.req("GET", "/api/catalog", key=AK)
        self.assertEqual((st_c, st_ai), (200, 200))
        self.assertEqual(body_c, body_ai)
        self.assertEqual(body_c.get("ok"), True)
        self.assertEqual(body_c.get("source"), "fixture")
        self.assertEqual(body_c.get("caps"), {"objeto": 20, "infectado": 10, "animal": 3, "actor": 2})
        for kind in KINDS:
            expected = sorted(_extract_names(cat_fixture["classes"][kind]))
            self.assertEqual(body_c["classes"][kind], expected)
            self.assertEqual(body_c["classes"][kind], sorted(body_c["classes"][kind]))
        self.assertEqual(body_c["wardrobes"], sorted(_extract_names(cat_fixture["wardrobes"])))
        self.assertEqual(
            body_c["emotes"], sorted(_extract_names(cat_fixture["emotes"], check_cert=True))
        )

    def test_catalogo_mezcla_tres_formas_y_filtra_caps_no_enteros(self):
        custom_cat = {
            "classes": {
                "objeto": [
                    "Z_Texto",
                    ["A_Par", "Base_Class"],
                    {"cls": "M_Dict", "cert": True},
                    {"cls": "Uncert_Obj", "cert": False},
                ],
                "infectado": [["Zmb_Dos", "Base"], "Zmb_Uno"],
                "animal": [{"cls": "Ani_Uno", "cert": True}],
                "actor": ["Act_Uno"],
            },
            "caps": {
                "objeto": 15,
                "infectado": "diez",
                "animal": True,
                "actor": 2.5,
                "combinado": 99,
            },
            "wardrobes": [["traje_b", "base"], "traje_a", {"cls": "traje_c"}],
            "emotes": [
                "EmoteUno",
                ["EmoteDos", "base"],
                {"cls": "EmoteTres", "cert": True},
                {"cls": "EmoteNoCert", "cert": False},
            ],
        }
        self.env.store.catalog = custom_cat
        st, body = self.env.req("GET", "/api/catalog", key=HK)
        self.assertEqual(st, 200)
        self.assertEqual(
            body["classes"]["objeto"],
            ["A_Par", "M_Dict", "Uncert_Obj", "Z_Texto"],
        )
        self.assertEqual(body["classes"]["infectado"], ["Zmb_Dos", "Zmb_Uno"])
        self.assertEqual(body["classes"]["animal"], ["Ani_Uno"])
        self.assertEqual(body["classes"]["actor"], ["Act_Uno"])
        self.assertEqual(body["caps"], {"objeto": 15})
        self.assertEqual(body["wardrobes"], ["traje_a", "traje_b", "traje_c"])
        self.assertEqual(body["emotes"], ["EmoteDos", "EmoteTres", "EmoteUno"])
        self.assertNotIn("EmoteNoCert", body["emotes"])

    def test_catalogo_negativos_credencial_host_y_query(self):
        st, _, _, body = raw(self.env, "GET", "/api/catalog")
        self.assertEqual((st, body.get("code")), (401, "unauthorized"))
        st, body = self.env.req("GET", "/api/catalog", host="evil.test")
        self.assertEqual((st, body.get("code")), (403, "forbidden"))
        st, body = self.env.req("GET", "/api/catalog?x=1")
        self.assertEqual((st, body.get("code")), (404, "not_found"))


class T2Esquema(ProfileBase):
    def test_esquema_positivo_igual_al_fichero(self):
        with open(ROOT / "schemas" / "scene.schema.json", encoding="utf-8") as f:
            expected = json.load(f)
        _, _, _, sid, _ = self.do_login()
        st_c, _, _, body_c = raw(
            self.env, "GET", "/api/schema", headers={"Cookie": cookie_header(self.env, sid)}
        )
        st_ai, body_ai = self.env.req("GET", "/api/schema", key=AK)
        self.assertEqual((st_c, st_ai), (200, 200))
        self.assertEqual(body_c, expected)
        self.assertEqual(body_ai, expected)
        st_q, body_q = self.env.req("GET", "/api/schema?x=1")
        self.assertEqual((st_q, body_q.get("code")), (404, "not_found"))

    def test_esquema_inexistente_o_basura_responde_503_y_backend_sigue_vivo(self):
        d = Path(tempfile.mkdtemp(prefix="dsbx-schema-"))
        self.addCleanup(shutil.rmtree, d, True)
        bad_json = d / "roto.json"
        bad_json.write_text("{no es json", encoding="utf-8")
        not_obj = d / "lista.json"
        not_obj.write_text("[1, 2, 3]", encoding="utf-8")
        for sp in (d / "no-existe.json", bad_json, not_obj):
            sub_dir = d / sp.stem
            sub_dir.mkdir(exist_ok=True)
            with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
                catalog = json.load(f)
            store = Store(str(sub_dir / "scene.json"), catalog)
            backend = Backend(store, HK, AK, port=0, log=io.StringIO(), schema_path=str(sp))
            t = threading.Thread(target=backend.serve_forever, daemon=True)
            t.start()
            try:
                fake_env = mock.Mock(port=backend.port, bodies=[])
                st, _, _, parsed = raw(
                    fake_env,
                    "GET",
                    "/api/schema",
                    headers={"Authorization": "Bearer " + HK},
                )
                self.assertEqual(st, 503, str(sp))
                self.assertEqual(parsed.get("ok"), False)
                self.assertEqual(parsed.get("code"), "schema_unavailable")
                st_scene, _, _, snap = raw(
                    fake_env,
                    "GET",
                    "/api/scene",
                    headers={"Authorization": "Bearer " + HK},
                )
                self.assertEqual(st_scene, 200)
                self.assertEqual(snap.get("rev"), 1)
            finally:
                backend.shutdown()


class T3IdaYVuelta(ProfileBase):
    def test_sin_fichero_y_guardar_con_cookie_y_bearer_persona(self):
        _, _, _, sid, csrf = self.do_login()
        hdrs = self.cookie_hdrs(sid, csrf)
        st, _, _, got0 = raw(self.env, "GET", "/api/profile", headers=hdrs)
        self.assertEqual(st, 200)
        self.assertEqual(got0, {"ok": True, "profile": None, "corrupt": False})
        self.assertFalse(self.profile_path.exists())

        prof1 = valid_profile(
            keymap={"aplicar": "Ctrl+Enter", "deshacer": None, "colocar": "G"},
            escena={"grid": {"root": "x"}},
            rodaje=None,
        )
        st, _, _, res1 = raw(self.env, "POST", "/api/profile", prof1, headers=hdrs)
        self.assertEqual((st, res1), (200, {"ok": True}))
        self.assertTrue(self.profile_path.exists())
        raw_bytes = self.profile_path.read_bytes()
        self.assertFalse(raw_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", raw_bytes)
        self.assertTrue(raw_bytes.endswith(b"\n"))

        st, _, _, got1 = raw(self.env, "GET", "/api/profile", headers=hdrs)
        self.assertEqual(st, 200)
        self.assertEqual(got1, {"ok": True, "profile": prof1, "corrupt": False})

        # Bearer de persona también guarda y el sobre `author` se quita antes de validar.
        prof2 = valid_profile(keymap={"aplicar": "Shift+F8"}, escena=None, rodaje={"r": 1})
        prof2_with_author = dict(prof2, author={"role": "human", "id": "web"})
        st, res2 = self.env.req("POST", "/api/profile", prof2_with_author, key=HK)
        self.assertEqual((st, res2), (200, {"ok": True}))
        st, got2 = self.env.req("GET", "/api/profile", key=HK)
        self.assertEqual((st, got2), (200, {"ok": True, "profile": prof2, "corrupt": False}))

        # Query string da 404.
        st_q, body_q = self.env.req("GET", "/api/profile?x=1", key=HK)
        self.assertEqual((st_q, body_q.get("code")), (404, "not_found"))


class T4Permisos(ProfileBase):
    def test_rechazos_csrf_origin_y_bearer_ia_sin_tocar_fichero(self):
        _, _, _, sid1, csrf1 = self.do_login()
        _, _, _, sid2, csrf2 = self.do_login()
        initial = valid_profile(keymap={"aplicar": "Ctrl+Enter"})
        st, _, _, _ = raw(
            self.env, "POST", "/api/profile", initial, headers=self.cookie_hdrs(sid1, csrf1)
        )
        self.assertEqual(st, 200)
        before_bytes = self.profile_path.read_bytes()
        before_mtime = self.profile_path.stat().st_mtime_ns

        other = valid_profile(keymap={"aplicar": "F2"})
        cookie1 = cookie_header(self.env, sid1)
        cookie_cases = [
            {"Cookie": cookie1, "Origin": good_origin(self.env)},
            {"Cookie": cookie1, "Origin": good_origin(self.env), "X-CSRF-Token": "malo"},
            {"Cookie": cookie1, "Origin": good_origin(self.env), "X-CSRF-Token": csrf2},
            {"Cookie": cookie1, "X-CSRF-Token": csrf1},
            {"Cookie": cookie1, "Origin": "http://evil.test", "X-CSRF-Token": csrf1},
        ]
        for hdrs in cookie_cases:
            st, _, _, parsed = raw(self.env, "POST", "/api/profile", other, headers=hdrs)
            self.assertEqual((st, parsed.get("code")), (403, "csrf_failed"), str(hdrs))
            self.assertEqual(self.profile_path.read_bytes(), before_bytes)
            self.assertEqual(self.profile_path.stat().st_mtime_ns, before_mtime)

        # Bearer de IA en GET y POST -> 403 forbidden (incluso si el cuerpo es inválido o grande).
        st_get_ai, body_get_ai = self.env.req("GET", "/api/profile", key=AK)
        self.assertEqual((st_get_ai, body_get_ai.get("code")), (403, "forbidden"))
        for bad_ai_body in (other, {"v": 999}, make_sized_profile(70000)[0]):
            st_post_ai, body_post_ai = self.env.req("POST", "/api/profile", bad_ai_body, key=AK)
            self.assertEqual((st_post_ai, body_post_ai.get("code")), (403, "forbidden"))
            self.assertEqual(self.profile_path.read_bytes(), before_bytes)
            self.assertEqual(self.profile_path.stat().st_mtime_ns, before_mtime)


class T5Forma(ProfileBase):
    def test_forma_positiva_y_cada_regla_negativa_con_pointer(self):
        minimal = {"v": 1, "layouts": {"escena": None, "rodaje": None}, "keymap": {}}
        st, res = self.env.req("POST", "/api/profile", minimal, key=HK)
        self.assertEqual((st, res), (200, {"ok": True}))
        before_bytes = self.profile_path.read_bytes()

        too_many_keys = {f"accion-{i}": "F2" for i in range(65)}
        cases = [
            (
                {"v": 1, "layouts": {"escena": None, "rodaje": None}, "keymap": {}, "sobra": 1},
                "/sobra",
            ),
            ({"v": 1, "layouts": {"escena": None, "rodaje": None}}, "/keymap"),
            ({"layouts": {"escena": None, "rodaje": None}, "keymap": {}}, "/v"),
            ({"v": 1, "keymap": {}}, "/layouts"),
            ({"v": 2, "layouts": {"escena": None, "rodaje": None}, "keymap": {}}, "/v"),
            ({"v": True, "layouts": {"escena": None, "rodaje": None}, "keymap": {}}, "/v"),
            ({"v": "1", "layouts": {"escena": None, "rodaje": None}, "keymap": {}}, "/v"),
            ({"v": 1, "layouts": [], "keymap": {}}, "/layouts"),
            (
                {
                    "v": 1,
                    "layouts": {"escena": None, "rodaje": None, "otro": {}},
                    "keymap": {},
                },
                "/layouts/otro",
            ),
            ({"v": 1, "layouts": {"escena": None}, "keymap": {}}, "/layouts/rodaje"),
            (
                {"v": 1, "layouts": {"escena": [], "rodaje": None}, "keymap": {}},
                "/layouts/escena",
            ),
            (
                {"v": 1, "layouts": {"escena": None, "rodaje": "mal"}, "keymap": {}},
                "/layouts/rodaje",
            ),
            ({"v": 1, "layouts": {"escena": None, "rodaje": None}, "keymap": []}, "/keymap"),
            (
                {
                    "v": 1,
                    "layouts": {"escena": None, "rodaje": None},
                    "keymap": too_many_keys,
                },
                "/keymap",
            ),
            (
                {
                    "v": 1,
                    "layouts": {"escena": None, "rodaje": None},
                    "keymap": {"Mayus": "F2"},
                },
                "/keymap/Mayus",
            ),
            (
                {
                    "v": 1,
                    "layouts": {"escena": None, "rodaje": None},
                    "keymap": {"aplicar": ""},
                },
                "/keymap/aplicar",
            ),
            (
                {
                    "v": 1,
                    "layouts": {"escena": None, "rodaje": None},
                    "keymap": {"aplicar": "A" * 41},
                },
                "/keymap/aplicar",
            ),
            (
                {
                    "v": 1,
                    "layouts": {"escena": None, "rodaje": None},
                    "keymap": {"aplicar": "Ctrl+\nEnter"},
                },
                "/keymap/aplicar",
            ),
        ]
        for bad_body, expected_ptr in cases:
            st, r = self.env.req("POST", "/api/profile", bad_body, key=HK)
            self.assertEqual(st, 400, (expected_ptr, bad_body, r))
            self.assertEqual(r.get("code"), "bad_profile", (expected_ptr, r))
            self.assertEqual(r.get("pointer"), expected_ptr, (bad_body, r))
            self.assertEqual(self.profile_path.read_bytes(), before_bytes)


class T6Tamano(ProfileBase):
    def test_65536_pasa_y_65537_da_413_sin_tocar_fichero(self):
        prof_ok, raw_ok = make_sized_profile(65536)
        st, r = self.env.req("POST", "/api/profile", raw=raw_ok, key=HK)
        self.assertEqual((st, r), (200, {"ok": True}))
        saved_bytes = self.profile_path.read_bytes()

        _, raw_big = make_sized_profile(65537)
        st_big, r_big = self.env.req("POST", "/api/profile", raw=raw_big, key=HK)
        self.assertEqual((st_big, r_big.get("code")), (413, "profile_too_large"))
        self.assertEqual(self.profile_path.read_bytes(), saved_bytes)


class T7Corrupto(ProfileBase):
    def test_fichero_corrupto_da_200_corrupt_true_y_post_valido_lo_arregla(self):
        bad_contents = [
            "{basura sin cerrar",
            "[1, 2, 3]",
            "123",
            json.dumps({"v": 2, "layouts": {"escena": None, "rodaje": None}, "keymap": {}}),
            json.dumps({"v": 1, "layouts": {"escena": [], "rodaje": None}, "keymap": {}}),
        ]
        for text in bad_contents:
            self.profile_path.write_text(text, encoding="utf-8")
            st, r = self.env.req("GET", "/api/profile", key=HK)
            self.assertEqual(st, 200, text)
            self.assertEqual(r, {"ok": True, "profile": None, "corrupt": True}, text)
            self.assertEqual(self.profile_path.read_text(encoding="utf-8"), text)

        fixed = valid_profile(keymap={"colocar": "Enter"})
        st, r = self.env.req("POST", "/api/profile", fixed, key=HK)
        self.assertEqual((st, r), (200, {"ok": True}))
        st, got = self.env.req("GET", "/api/profile", key=HK)
        self.assertEqual((st, got), (200, {"ok": True, "profile": fixed, "corrupt": False}))


class T8Atomico(ProfileBase):
    def test_fallo_en_os_replace_responde_500_conserva_anterior_y_limpia_tmp(self):
        initial = valid_profile(keymap={"aplicar": "Ctrl+Enter"})
        st, _ = self.env.req("POST", "/api/profile", initial, key=HK)
        self.assertEqual(st, 200)
        before_bytes = self.profile_path.read_bytes()
        before_files = set(os.listdir(self.env.dir))

        replacement = valid_profile(keymap={"aplicar": "Shift+F8"})
        with mock.patch.object(profile_mod.os, "replace", side_effect=OSError("disco lleno")):
            st, r = self.env.req("POST", "/api/profile", replacement, key=HK)
        self.assertEqual((st, r.get("code")), (500, "internal"))
        self.assertEqual(self.profile_path.read_bytes(), before_bytes)
        after_files = set(os.listdir(self.env.dir))
        self.assertEqual(after_files, before_files)


class T9Secretos(ProfileBase):
    def test_sin_secretos_en_log_ni_en_profile_json(self):
        _, _, _, sid, csrf = self.do_login()
        hdrs = self.cookie_hdrs(sid, csrf)
        prof = valid_profile(keymap={"aplicar": "Ctrl+Enter", "deshacer": None})
        st, _, _, _ = raw(self.env, "POST", "/api/profile", prof, headers=hdrs)
        self.assertEqual(st, 200)
        raw(self.env, "GET", "/api/profile", headers=hdrs)
        raw(self.env, "GET", "/api/catalog", headers=hdrs)
        raw(self.env, "GET", "/api/schema", headers=hdrs)

        file_text = self.profile_path.read_text(encoding="utf-8")
        log_text = self.env.log.getvalue()
        with self.env.backend._sessions_lock:
            sids = list(self.env.backend.sessions.keys())
            csrfs = [info["csrf"] for info in self.env.backend.sessions.values()]
        for secret in [HK, AK] + sids + csrfs:
            self.assertTrue(bool(secret))
            self.assertNotIn(secret, file_text)
            self.assertNotIn(secret, log_text)


class T10RutasDistintas(unittest.TestCase):
    def test_misma_carpeta_nombres_distintos_arranca_y_mismo_fichero_lanza_value_error(self):
        d = Path(tempfile.mkdtemp(prefix="dsbx-t10-"))
        self.addCleanup(shutil.rmtree, d, True)
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)

        # Positivo: scene.json y profile.json en la misma carpeta.
        scene_ok = d / "scene.json"
        store_ok = Store(str(scene_ok), copy.deepcopy(catalog))
        backend_ok = Backend(store_ok, HK, AK, port=0, log=io.StringIO())
        try:
            self.assertNotEqual(
                os.path.normcase(os.path.abspath(backend_ok.profile.path)),
                os.path.normcase(os.path.abspath(scene_ok)),
            )
        finally:
            backend_ok.httpd.server_close()

        # Negativo 1: escena llamada profile.json sin profile_path.
        sub = d / "colision"
        sub.mkdir()
        scene_named_profile = sub / "profile.json"
        store_col = Store(str(scene_named_profile), copy.deepcopy(catalog))
        scene_bytes_before = scene_named_profile.read_bytes()
        with self.assertRaises(ValueError):
            Backend(store_col, HK, AK, port=0, log=io.StringIO())
        self.assertEqual(scene_named_profile.read_bytes(), scene_bytes_before)

        # Negativo 2: profile_path explícito igual a la ruta de la escena.
        scene_ok_bytes = scene_ok.read_bytes()
        with self.assertRaises(ValueError):
            Backend(store_ok, HK, AK, port=0, log=io.StringIO(), profile_path=str(scene_ok))
        self.assertEqual(scene_ok.read_bytes(), scene_ok_bytes)


if __name__ == "__main__":
    unittest.main()
