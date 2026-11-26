"""Escena viva en el backend (F2-offline §4.2-§4.6): SceneLive.

Gestiona el estado de catalogo del servidor actual (D4), la preparacion y el
encolado de ordenes F2 (`scene.apply`, `scene.reset`, `scene.observe`), las
transiciones de §4.4, la reconciliacion y la compensacion de §4.5, y la ultima
observacion `now` (§4.2).

Solo biblioteca estandar. Disenado para probarse mediante llamadas directas
bajo `bridge.cond` / `store.lock` sin modificar `bridge.py` ni `server.py`,
y listo para que la tanda F2-3 cablee los ganchos de §4.6.

API publica para los ganchos de §4.6 (todos los metodos `*_locked` suponen
`bridge.lock` / `bridge.cond` tomado):
- `on_server_hello_locked(peer_record)`: registra la presentacion del peer
  servidor (`inst`, `conn`, capacidad `scene` exactamente el entero 1, A7) e
  invalida la certificacion previa del catalogo del mundo (D4).
- `on_catalog_complete_locked(inst, build)`: certifica el catalogo recien
  completado si es el mismo `inst` y la misma `conn` que el servidor vigente
  (A1: la `build` no se compara; en el hello es `retail`/`diag` y en la pagina
  de catalogo es texto libre).
- `catalog_ok_locked() -> bool`: indica si `bridge.catalog` es valido para el
  servidor presentado ahora.
- `server_has_scene_locked() -> bool`: indica si hay un peer servidor activo
  y no perdido con capacidad `scene` exactamente `1` (D1, A7).
- `state_read_args_locked() -> dict`: devuelve `{"f2": 1, "doc_id": doc_id}` si el
  servidor soporta escena o `{}` si no (§3.2, D1; v1.3 §3.5).
- `prepare_apply_locked(doc, rev, hash_) -> dict`: valida el documento
  congelado con §4.1; devuelve `{"ok": True, "plan": ..., "expectation": ...,
  "envelope": ...}` o `{"ok": False, "code": ..., "http": ..., "pointer": ...,
  "msg": ..., "errors": [...]}` sin crear orden ni emitir eventos. Falla
  cerrado (A6): exige servidor con escena y `caps` validos.
- `enqueue_apply_locked(op_id, plan, expectation=None) -> (bool, order|err)`:
  encola una orden F2 `scene.apply` con el plan y guarda su expectativa (D11).
  Acepta tanto el `plan` pelado como el dict que devuelve `prepare_apply_locked`.
  La expectativa es obligatoria (A6: no hay plan B con el documento vivo); si
  falta, es un error. Si `op_id` no existe en `backend.ops`, crea el registro
  `pendiente` y emite `op.state` (sin `verb`: §4.2).
- `enqueue_reset_locked(op_id, doc_id) -> (bool, order|err)`: crea la orden de
  API `scene.reset` con `verb: "scene.reset"`, `rev: None`, `hash: None` y la
  encola en el bridge (§4.2). Las precondiciones `doc_changed`,
  `scene_unsupported` y `queue_full` (que cuenta `scene.reset`) viven aqui
  (A11). Sin peer servidor se encola igual (terminara `no_entregada`).
- `request_observe_locked(doc_id) -> dict`: valida `doc_id` y soporte `scene`
  y encola la orden interna `scene.observe {doc_id, at: "now"}`; devuelve
  `{"ok": True, "read_id": ...}` o el error 409 correspondiente. Como mucho
  hay un observe `now` en vuelo y las peticiones de mas reciben su `read_id`
  (A9).
- `observation_locked() -> dict`: devuelve `{"ok": True, "observation": ...,
  "age_ms": ...}` con `age_ms` medido con el reloj del bridge (§4.2).
- `is_f2_order(order) -> bool`: determina por la propia orden si su contrato
  es F2 (D1, DP-5). Solo los verbos `scene.*`; `state.read` nunca (P-01). Un
  `scene.apply` F1 (solo `doc_id`, `rev`, `hash`, sin `args.f2`) no lo es.
- `valid_read(order, read) -> bool`: valida la forma y los rangos de §3.2 y
  §3.6 para el resultado de una orden F2. Acepta `generation.rev` de hasta 9
  digitos (A2).
- `on_result_locked(order, status, reason, read) -> bool`: aplica las
  transiciones de §4.4 a una orden F2 (de API o interna) y devuelve si la ha
  tratado. Contrato A10: `handle_result` lo llama **antes** de marcar
  `result_seen`; este metodo no lo marca. Las internas (`rd-N`) nunca llaman a
  `set_op_state`.
- `on_world_read_locked(read)`: reconcilia o compensa las ordenes F2 en
  `parcial` sin resolver del mismo `epoch` (§4.5). Solo juzga lecturas que
  reconcilian: epoch del servidor presentado y conexion no perdida (A5).
- `has_unresolved_locked() -> bool`: indica si queda alguna orden F2 de esta
  sesion en `parcial` no terminal y del mismo `epoch` que el servidor actual,
  sea cual sea su `conn` (§4.5, F1-03).

Decisiones de hilo (documentadas por el hallazgo 13 de RONDA2):
- A8: un primer resultado tardio de una orden `parcial/mundo_reiniciado` se
  aplica igual que en F1b-bridge §2.5.4. `mundo_reiniciado` no es terminal para
  `on_result_locked`; si lo es para la reconciliacion (§4.4).
- A9: un unico observe `now` en vuelo; las peticiones de mas reciben el mismo
  `read_id`.
- Compensacion (§4.5 / A13): cuenta toda compensacion entregada (la interna con
  `delivered_inst` puesto), tambien una `rejected` y tambien una cuyo resultado
  se pierde y termina en `descartada` por caducidad. Al encolar una compensacion
  se guarda en la orden objetivo la clave de la interna en `bridge.orders`
  (`(session, op_id)`) y su `comp_request_n`. En la lectura: si la ultima
  entregada sigue en vuelo (`pendiente` o `ejecutando`) no se juzga; si hay
  `MAX_COMPENSATIONS` entregadas o mas -> `parcial/interrumpida`; si la ultima
  entregada ya termino (resultado, caducidad o descarte) y `pending.n` es igual
  a su `comp_request_n` -> sin progreso -> `parcial/interrumpida`; si no, se
  encola otra. `target["compensations"]` es el numero de entregadas. Sin
  progreso, la orden pasa a `parcial/interrumpida`, terminal, con `origin`
  `backend`; nunca a `fallido` (hallazgo 2). Una compensacion que sale `fallido`
  deja la orden del bridge en `terminal` (C-02).
"""
import copy
import math
import time

from app.backend.actor_judge import judge_identity
from app.backend.actor_wire import valid_actor_read
from app.backend.scene_plan import (
    check_apply_predicate,
    evaluate_compensation_predicate,
    evaluate_reset_predicate,
    obs_now_row_to_m,
    plan_args_error,
    valid_scene_read,
    validate_for_apply,
)

# Contrato v1.3 (brief de F2-partida §3.5, P-01): la marca `args.f2 == 1` solo cuenta en
# estos verbos. `state.read` nunca es una orden F2 en el backend, lleve o no `f2`.
F2_VERBS = ("scene.apply", "scene.reset", "scene.observe")
# F3-offline-2 §4: los verbos de actor van siempre como ordenes internas con la marca F2.
ACTOR_VERBS = ("actor.apply", "actor.reset", "actor.observe")
F2_VERBS = F2_VERBS + ACTOR_VERBS
# §4.2: motivo de la operacion segun el primer actor que no da `ok`.
_ACTOR_STAGE_REASON = {"no_cumple": "actor_no_cumple", "rechazado": "actor_rechazado",
                       "error": "actor_error"}
_ACTOR_POS_TOL_MM = 500
# §3.3 v1.3: `if_pending` va siempre (DP-2); vacio es un reset normal.
EMPTY_IF_PENDING = {"session": "", "op_id": ""}


def _if_pending_target(args):
    """`if_pending` de una compensacion, o None si es un reset normal (vacio o ausente)."""
    ip = args.get("if_pending") if isinstance(args, dict) else None
    if isinstance(ip, dict) and (ip.get("session") or ip.get("op_id")):
        return ip
    return None


# Terminales para la reconciliacion (§4.4/§4.5). `mundo_reiniciado` no se
# reconcilia ni se compensa: la orden es de otro epoch. `superada` es la salida
# de A12. `interrumpida` y `contenido_ajeno` son terminales (§4.4).
TERMINAL_PARCIAL_REASONS = (
    "contenido_ajeno",
    "compensada",
    "interrumpida",
    "superada",
    "mundo_reiniciado",
)
# Un primer resultado tardio si se aplica sobre `mundo_reiniciado` (A8).
RESULT_BLOCKING_REASONS = ("contenido_ajeno", "compensada", "interrumpida", "superada")

MAX_COMPENSATIONS = 3
_MAX_REV9 = 999999999
_MAX_COUNT = 999999


def _now_ms():
    return int(time.time() * 1000)


def _is_int(val):
    return isinstance(val, int) and not isinstance(val, bool)


def _scene_cap(val):
    """Capacidad `scene`: exactamente el entero JSON 1 (A7)."""
    return _is_int(val) and val == 1


def _valid_read_compat(read, require_obs=None, world_size=99999):
    """Valida el read con las reglas de scene_plan, admitiendo `rev` de 9 digitos (A2).

    `valid_scene_read` de scene_plan (foto parcial) exige `generation.rev` en
    [0, 999999]. A2 fija hasta 9 digitos. Se valida una copia con `rev` 0 solo
    para la forma; las comparaciones de identidad usan el read original.
    """
    try:
        if valid_scene_read(read, require_obs=require_obs, world_size=world_size):
            return True
    except Exception:
        return False
    if not isinstance(read, dict):
        return False
    gen = read.get("generation")
    if not (isinstance(gen, dict) and _is_int(gen.get("rev"))
            and 0 <= gen["rev"] <= _MAX_REV9):
        return False
    patched = copy.deepcopy(read)
    patched["generation"]["rev"] = 0
    try:
        return valid_scene_read(patched, require_obs=require_obs, world_size=world_size)
    except Exception:
        return False


def _normalized_for_predicate(order, read):
    """Copia (orden, read) con `rev` 0 cuando solo falla la cota de 9 digitos (A2)."""
    if not isinstance(read, dict) or not isinstance(order, dict):
        return order, read
    gen = read.get("generation")
    args = order.get("args")
    if not isinstance(gen, dict) or not isinstance(args, dict):
        return order, read
    rev = gen.get("rev")
    arev = args.get("rev")
    if _is_int(rev) and _is_int(arev) and rev == arev and not (0 <= rev <= _MAX_COUNT):
        order2 = copy.deepcopy(order)
        read2 = copy.deepcopy(read)
        order2["args"]["rev"] = 0
        read2["generation"]["rev"] = 0
        return order2, read2
    return order, read


def _apply_predicate(order, read, world_size):
    try:
        if check_apply_predicate(order, read, world_size=world_size):
            return True
    except Exception:
        pass
    order2, read2 = _normalized_for_predicate(order, read)
    if order2 is order and read2 is read:
        return False
    try:
        return check_apply_predicate(order2, read2, world_size=world_size)
    except Exception:
        return False


def _reset_predicate(order, read, world_size):
    try:
        return evaluate_reset_predicate(order, read, world_size=world_size)
    except Exception:
        pass
    order2, read2 = _normalized_for_predicate(order, read)
    if order2 is order and read2 is read:
        return ("fallido", "lectura_no_cumple")
    try:
        return evaluate_reset_predicate(order2, read2, world_size=world_size)
    except Exception:
        return ("fallido", "lectura_no_cumple")


def _stopped_apply_predicate(order, read, world_size):
    """Predicado de «apply detenido» (§4.3): usa el de scene_plan.

    `evaluate_compensation_predicate` ya hace el «apply detenido» con `n >=
    retained_n >= 1`, `generation` nula y `pending` de la orden como «sin
    resolver». Se normaliza el `rev` de 9 digitos (A2) como en el resto de
    predicados; no queda copia local de la logica.
    """
    order2, read2 = _normalized_for_predicate(order, read)
    try:
        return evaluate_compensation_predicate(order2, read2, world_size=world_size)
    except Exception:
        return ("fallido", "lectura_no_cumple")


class SceneLive:
    """Coordinador de escena viva (F2) acoplado a un Bridge y su Backend."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.backend = bridge.backend
        self._catalog_valid = False
        self._catalog_inst = None
        self._catalog_conn = None
        self._observe_now_op_id = None
        self._observation = None
        self._observation_mono = None
        # F3-offline-2 §4-§5: etapa de actores por operacion, veredicto de la escena en
        # el reset y la ultima lectura de actores.
        self._stage = {}
        self._reset_verdict = {}
        self._actor_observe_op_id = None
        self._actor_observation = None
        self._actor_observation_mono = None

    # --- D1 y D4: capacidades del peer servidor y catalogo ----------------

    def on_server_hello_locked(self, peer_record):
        """Gancho tras `handle_hello` del servidor: capacidad scene e invalidacion del catalogo (D4)."""
        srv = self.bridge.peers.get("server")
        rec = peer_record if isinstance(peer_record, dict) else (srv or {})
        if srv is not None:
            # F2-3 guarda `scene` en el registro del peer; este hook lo respeta y,
            # si aun no esta, lo copia de la presentacion recibida.
            if "scene" not in srv and "scene" in rec:
                srv["scene"] = rec.get("scene")
        self._catalog_valid = False
        self._catalog_inst = None
        self._catalog_conn = None

    def on_catalog_complete_locked(self, inst, build):
        """Gancho tras completar `Bridge.catalog`: certifica el catalogo para el servidor actual (D4/A1)."""
        srv = self.bridge.peers.get("server")
        if srv is None or srv.get("lost"):
            self._catalog_valid = False
            return False
        if srv.get("inst") != inst:
            self._catalog_valid = False
            return False
        cat = self.bridge.catalog
        if not isinstance(cat, dict):
            self._catalog_valid = False
            return False
        # A1: la build no se compara. El catalogo vale por `inst` y por haberse
        # completado despues del ultimo hello (misma `conn`).
        self._catalog_valid = True
        self._catalog_inst = inst
        self._catalog_conn = srv.get("conn")
        return True

    def catalog_ok_locked(self):
        """True solo si hay un catalogo completado para el hello vigente del servidor (D4/A1)."""
        if not self._catalog_valid:
            return False
        srv = self.bridge.peers.get("server")
        cat = self.bridge.catalog
        if srv is None or srv.get("lost") or not isinstance(cat, dict):
            return False
        if srv.get("inst") != self._catalog_inst:
            return False
        if srv.get("conn") != self._catalog_conn:
            return False
        return True

    def server_has_scene_locked(self):
        """True si el servidor actual esta activo y se presento con `scene` == 1 (D1/A7)."""
        srv = self.bridge.peers.get("server")
        if srv is None or srv.get("lost"):
            return False
        return _scene_cap(srv.get("scene"))

    def _world_size_locked(self):
        srv = self.bridge.peers.get("server")
        if isinstance(srv, dict) and isinstance(srv.get("world_size"), (int, float)) \
                and not isinstance(srv.get("world_size"), bool):
            return srv["world_size"]
        return 0

    def state_read_args_locked(self):
        """Devuelve `{"f2": 1, "doc_id": ...}` si el servidor tiene escena o `{}` si no.

        v1.3 (§3.5): la marca le sirve solo al mod, para anadir el bloque `scene`. En el
        backend `state.read` nunca es F2 (P-01): `is_f2_order` no mira su `args.f2`.
        """
        if not self.server_has_scene_locked():
            return {}
        snap = self.backend.store.snapshot()
        return {"f2": 1, "doc_id": snap["doc_id"]}

    # --- Preparacion y encolado de ordenes F2 -----------------------------

    def _error(self, code, http, msg, pointer=""):
        return {
            "ok": False,
            "code": code,
            "http": http,
            "pointer": pointer,
            "msg": msg,
            "errors": [{"code": code, "pointer": pointer, "msg": msg}],
        }

    def prepare_apply_locked(self, doc, rev, hash_):
        """Valida el documento congelado (§4.1) y devuelve el plan + expectativa o el error.

        Pasa a `validate_for_apply` el `op_id` que asignara `_new_api_op` y la `conn`
        del servidor presentado (C-06). La secuencia de errores es la de §4.1: los
        topes los valida `validate_for_apply` en su paso 5 (C-07).
        """
        if not self.server_has_scene_locked():
            return self._error("scene_unsupported", 409, "El servidor presentado no soporta escena F2")
        catalog_valid = self.catalog_ok_locked()
        srv = self.bridge.peers.get("server")
        conn = srv.get("conn") if isinstance(srv, dict) else None
        return validate_for_apply(
            doc=doc,
            rev=rev,
            hash_=hash_,
            store_catalog=self.backend.store.catalog,
            world_catalog=self.bridge.catalog,
            catalog_valid=catalog_valid,
            world_size=self._world_size_locked(),
            op_id="op-%d" % (self.backend._op_n + 1),
            conn=conn,
            actor_engine=self._actor_engine_locked(),
        )

    def _new_api_op(self, op_id, rev, hash_, verb=None):
        if op_id is None:
            self.backend._op_n += 1
            op_id = "op-%d" % self.backend._op_n
        if op_id in self.backend.ops:
            return op_id, self.backend.ops[op_id], False
        op = {
            "op_id": op_id,
            "state": "pendiente",
            "rev": rev,
            "hash": hash_,
            "at_ms": _now_ms(),
            "origin": "backend",
            "reason": None,
        }
        if verb is not None:
            op["verb"] = verb
        self.backend.ops[op_id] = op
        self.backend.op_mono[op_id] = self.bridge._now()
        self.backend._emit("op.state", dict(op))
        return op_id, op, True

    def enqueue_apply_locked(self, op_id, plan, expectation=None, actor_orders=None):
        """Encola una orden F2 `scene.apply` con `plan` y `expectation` (D11).

        F3-offline-2 §4.1: `actor_orders` (o la clave de la respuesta de validacion)
        se guarda en la orden para la etapa de actores.
        """
        if isinstance(plan, dict) and "plan" in plan and "ok" in plan:
            if expectation is None:
                expectation = plan.get("expectation")
            if actor_orders is None:
                actor_orders = plan.get("actor_orders")
            plan = plan["plan"]
        actor_orders = list(actor_orders or [])
        if actor_orders and self._actor_engine_locked() != "expansion":
            # C5 (§3): la capacidad se perdio entre validar y encolar.
            return False, self._error("expansion_unavailable", 422,
                                      "El servidor ya no tiene motor de actores")
        if not self.server_has_scene_locked():
            return False, self._error("scene_unsupported", 409, "El servidor presentado no soporta escena F2")
        if not isinstance(plan, dict) or not isinstance(expectation, dict):
            # A6: la expectativa sale siempre del documento congelado; no hay plan B.
            return False, self._error("bad_args", 422, "Falta la expectativa del documento congelado", "/expectation")
        bad_key = plan_args_error(plan)
        if bad_key is not None:
            # DP-2 (v1.3): una orden sin alguna clave, o con columnas desalineadas, no se manda.
            return False, self._error("bad_plan", 422, "El plan no tiene la forma v1.3 completa", bad_key)
        op_id, _op, _new = self._new_api_op(
            op_id, plan.get("rev"), plan.get("hash"), verb=None,
        )
        ok, order = self.bridge.enqueue_order("scene.apply", plan, op_id=op_id, internal=False)
        if not ok:
            return False, self._error("wire_cap_exceeded", 500, "La orden no cabe en el cable")
        order["f2"] = True
        order["expectation"] = copy.deepcopy(expectation)
        order["actor_orders"] = copy.deepcopy(actor_orders)
        return True, order

    def _scene_queue_len_locked(self):
        n = 0
        for o in self.bridge.orders.values():
            if o.get("internal"):
                continue
            if o.get("verb") in ("scene.apply", "scene.reset") \
                    and o.get("bstate") in ("pendiente", "ejecutando"):
                n += 1
        return n

    def enqueue_reset_locked(self, op_id, doc_id):
        """Crea la orden de API `scene.reset` y la encola en el bridge (§4.2/A11)."""
        snap = self.backend.store.snapshot()
        if doc_id != snap["doc_id"]:
            return False, self._error("doc_changed", 409, "documento distinto", "/doc_id")
        srv = self.bridge.peers.get("server")
        if srv is not None and not srv.get("lost") and not self.server_has_scene_locked():
            return False, self._error("scene_unsupported", 409, "El servidor presentado no soporta escena F2")
        if self._scene_queue_len_locked() >= self.bridge.queue_max:
            return False, self._error("queue_full", 409, "Cola del bridge llena", "")
        op_id, _op, _new = self._new_api_op(op_id, None, None, verb="scene.reset")
        # §3.3 v1.3: todas las claves siempre; `if_pending` vacio es un reset normal.
        args = {"f2": 1, "doc_id": doc_id, "if_pending": dict(EMPTY_IF_PENDING)}
        ok, order = self.bridge.enqueue_order("scene.reset", args, op_id=op_id, internal=False)
        if not ok:
            return False, self._error("wire_cap_exceeded", 500, "La orden no cabe en el cable")
        order["f2"] = True
        # La fila pudo existir antes (p. ej. un apply reutilizado): el verbo manda.
        self.backend.ops[op_id]["verb"] = "scene.reset"
        return True, order

    def request_observe_locked(self, doc_id):
        """Encola una lectura interna `scene.observe {doc_id, at: "now"}` (§4.2/A9)."""
        snap = self.backend.store.snapshot()
        if doc_id != snap["doc_id"]:
            return self._error("doc_changed", 409, "documento distinto", "/doc_id")
        if not self.server_has_scene_locked():
            return self._error("scene_unsupported", 409, "El servidor no soporta escena F2")
        if self._observe_now_op_id is not None:
            active = self.bridge.orders.get((self.bridge.session, self._observe_now_op_id))
            if active is not None and active.get("bstate") in ("pendiente", "ejecutando"):
                return {"ok": True, "read_id": active["op_id"]}
            self._observe_now_op_id = None
        ok, order = self.bridge.enqueue_order(
            "scene.observe",
            {"f2": 1, "doc_id": doc_id, "at": "now"},
            internal=True,
        )
        if not ok:
            return self._error("wire_cap_exceeded", 500, "La orden no cabe en el cable")
        order["f2"] = True
        order["purpose"] = "observe_now"
        self._observe_now_op_id = order["op_id"]
        return {"ok": True, "read_id": order["op_id"]}

    def request_actor_observe_locked(self, doc_id):
        """F3-offline-2 §5: lectura interna `actor.observe`, una sola en vuelo."""
        snap = self.backend.store.snapshot()
        if doc_id != snap["doc_id"]:
            return self._error("doc_changed", 409, "documento distinto", "/doc_id")
        if self._actor_engine_locked() != "expansion":
            return self._error("expansion_unavailable", 409, "El servidor no tiene motor de actores")
        if self._actor_observe_op_id is not None:
            active = self.bridge.orders.get((self.bridge.session, self._actor_observe_op_id))
            if active is not None and active.get("bstate") in ("pendiente", "ejecutando"):
                return {"ok": True, "read_id": active["op_id"]}
            self._actor_observe_op_id = None
        ok, order = self.bridge.enqueue_order(
            "actor.observe", {"f2": 1, "doc_id": doc_id}, internal=True)
        if not ok:
            return self._error("wire_cap_exceeded", 500, "La orden no cabe en el cable")
        order["f2"] = True
        order["purpose"] = "actor_observe"
        self._actor_observe_op_id = order["op_id"]
        return {"ok": True, "read_id": order["op_id"]}

    def actor_observation_locked(self):
        """F3-offline-2 §5: ultima foto de actores valida y su `age_ms` (o null)."""
        if self._actor_observation is None or self._actor_observation_mono is None:
            return {"ok": True, "observation": None, "age_ms": None}
        age_ms = int((self.bridge._now() - self._actor_observation_mono) * 1000)
        return {"ok": True, "observation": copy.deepcopy(self._actor_observation),
                "age_ms": age_ms}

    def observation_locked(self):
        """Devuelve la ultima observacion `now` y su `age_ms` medido con el reloj del bridge (§4.2)."""
        if self._observation is None or self._observation_mono is None:
            return {"ok": True, "observation": None, "age_ms": None}
        age_ms = int((self.bridge._now() - self._observation_mono) * 1000)
        return {
            "ok": True,
            "observation": copy.deepcopy(self._observation),
            "age_ms": age_ms,
        }

    # --- Clasificacion y validacion de resultados F2 ----------------------

    def is_f2_order(self, order):
        """Determina si una orden tiene contrato F2 (D1, DP-5).

        Solo los verbos `scene.apply`, `scene.reset` y `scene.observe` pueden ser F2.
        `state.read` nunca lo es, aunque lleve `args.f2 = 1` (P-01, §3.5): su resultado
        sigue el camino comun de lecturas del bridge, que pone `reconciled` y llama a
        `on_world_read_locked`. En los verbos de escena cuenta la marca de la orden del
        backend y, en el cable, `args.f2 == 1` (DP-5); un `scene.apply` F1 (solo `doc_id`,
        `rev` y `hash`) no la lleva.
        """
        if not isinstance(order, dict):
            return False
        verb = order.get("verb")
        if verb not in F2_VERBS:
            return False
        if "f2" in order:
            return bool(order["f2"])
        args = order.get("args")
        if isinstance(args, dict) and _is_int(args.get("f2")) and args["f2"] == 1:
            return True
        return verb in ("scene.reset", "scene.observe")

    def valid_read(self, order, read):
        """Valida la forma y los rangos del `read` de una orden F2 (§3.2, §3.6, A2)."""
        if not self.is_f2_order(order):
            return False
        verb = order.get("verb")
        if verb in ACTOR_VERBS:
            # §4: la foto de actor la juzga SceneLive; el bridge no la corta.
            return isinstance(read, dict)
        args = order.get("args") or {}
        require_obs = None
        if verb == "scene.apply":
            require_obs = "checkpoint"
        elif verb == "scene.observe":
            require_obs = args.get("at")
            if require_obs not in ("checkpoint", "now"):
                return False
        if not _valid_read_compat(read, require_obs=require_obs, world_size=self._world_size_locked()):
            return False
        doc_id = args.get("doc_id")
        if doc_id and read["scene"].get("doc_id") != doc_id:
            return False
        return True

    def valid_state_read_locked(self, order, read):
        """T-01: un `state.read` con `args.f2 == 1` solo reconcilia con su bloque `scene` valido.

        Lo llama el bridge antes de dar la lectura por buena (§3.6, §3.9 e). No convierte
        `state.read` en una orden F2 (P-01): su resultado sigue el camino comun de lecturas.
        Un `state.read` sin la marca (F1, peer sin escena) no se valida aqui.
        """
        args = order.get("args") if isinstance(order, dict) else None
        if not (isinstance(args, dict) and _is_int(args.get("f2")) and args["f2"] == 1):
            return True
        if not _valid_read_compat(read, require_obs=None, world_size=self._world_size_locked()):
            return False
        return read["scene"].get("doc_id") == args.get("doc_id")

    # --- Resultados directos (§4.4) ---------------------------------------

    def on_result_locked(self, order, status, reason, read):
        """Juzga el resultado de una orden F2 (de API o interna). Contrato A10: no marca `result_seen`."""
        if not self.is_f2_order(order):
            return False
        if order.get("result_seen"):
            return True
        if order.get("bstate") in ("descartada", "terminal"):
            return True
        if order.get("bstate") not in ("ejecutando", "parcial"):
            return False

        if order.get("internal"):
            order["bstate"] = "terminal"
            self._handle_internal_result_locked(order, status, reason, read)
            self.bridge.cond.notify_all()
            return True

        op_id = order["op_id"]
        op = self.backend.ops.get(op_id)
        if op is None:
            return False
        if op["state"] in ("observado", "fallido", "aplicado") or (
            op["state"] == "parcial" and op.get("reason") in RESULT_BLOCKING_REASONS
        ):
            # Resultado tardio de una orden ya cerrada: se acusa y no cambia nada.
            order["bstate"] = "terminal"
            return True

        verb = order.get("verb")
        wsize = self._world_size_locked()

        if status == "done":
            order["bstate"] = "terminal"
            self.backend.set_op_state(op_id, "aplicado", "servidor", None)
            if verb == "scene.apply":
                if _apply_predicate(order, read, wsize):
                    self._close_apply_ok_locked(order, None)
                else:
                    self.backend.set_op_state(op_id, "fallido", "servidor", "lectura_no_cumple")
            elif verb == "scene.reset":
                st, rsn = _reset_predicate(order, read, wsize)
                self._close_reset_locked(order, st, rsn)
        elif status == "rejected":
            order["bstate"] = "terminal"
            # A14: un rechazo no toca last, pending, generation ni retained.
            self.backend.set_op_state(op_id, "fallido", "servidor", reason)
        elif status == "error":
            order["bstate"] = "parcial"
            self.backend.set_op_state(op_id, "parcial", "servidor", reason)
            self._maybe_trigger_read_locked(order)

        self.bridge.cond.notify_all()
        return True

    def _maybe_trigger_read_locked(self, order):
        srv = self.bridge.peers.get("server")
        if srv and not srv.get("lost") and order.get("epoch") == srv.get("epoch"):
            self.bridge._trigger_state_read_locked()

    def _handle_internal_result_locked(self, order, status, reason, read):
        verb = order.get("verb")
        args = order.get("args") or {}
        wsize = self._world_size_locked()

        purpose = order.get("purpose")
        if purpose == "actor_stage":
            self._on_actor_stage_result_locked(order, status, read, wsize)
            return
        if purpose == "actor_reset":
            self._on_actor_reset_result_locked(order, status, read, wsize)
            return
        if purpose == "actor_observe":
            if self._actor_observe_op_id == order.get("op_id"):
                self._actor_observe_op_id = None
            if status == "done" and valid_actor_read(read, world_size=wsize):
                self._actor_observation = copy.deepcopy(read)
                self._actor_observation_mono = self.bridge._now()
            return

        if verb == "scene.observe" and args.get("at") == "now":
            if self._observe_now_op_id == order.get("op_id"):
                self._observe_now_op_id = None
            if status != "done" or not self.valid_read(order, read):
                return
            if read.get("epoch") != order.get("epoch"):
                return
            obs_obj = {
                "read_id": order["op_id"],
                "doc_id": read["scene"]["doc_id"],
                "epoch": read["epoch"],
                "generation": copy.deepcopy(read["generation"]),
                # §3.8 v1.3: la API sigue en metros; las filas llegan en mm y se convierten aqui.
                "rows": [obs_now_row_to_m(r) for r in read["obs"]["rows"]],
                "at_ms": _now_ms(),
                "origin": "servidor",
            }
            self._observation = obs_obj
            self._observation_mono = self.bridge._now()
            self.backend.observation = copy.deepcopy(obs_obj)
            self.backend._emit("scene.observation", copy.deepcopy(obs_obj))
            return

        if verb == "scene.observe" and args.get("at") == "checkpoint":
            if status != "done" or not self.valid_read(order, read):
                return
            if read.get("epoch") != order.get("epoch"):
                return
            target = self._find_unresolved_order_locked(order.get("target_op_id"))
            if target is None or target.get("verb") != "scene.apply":
                return
            if target.get("epoch") != read.get("epoch"):
                return
            gen = read.get("generation")
            # §4.5: si el resultado ensena otra generacion, la orden no cambia.
            if not isinstance(gen, dict):
                return
            if gen.get("session") != target.get("session") or gen.get("op_id") != target.get("op_id"):
                return
            if _apply_predicate(target, read, wsize):
                self._close_apply_ok_locked(target, "reconciliada")
            else:
                self.backend.set_op_state(target["op_id"], "fallido", "servidor", "lectura_no_cumple")
            target["bstate"] = "terminal"
            return

        if verb == "scene.reset" and _if_pending_target(args) is not None:
            # A13: el conteo de compensaciones entregadas se hace en la lectura
            # (§4.5), no aqui. C-02: una compensacion que resuelve en `fallido`
            # tambien deja la orden del bridge en `terminal`. v1.3: un `if_pending`
            # vacio es un reset normal, no una compensacion.
            target = self._find_unresolved_order_locked(
                order.get("target_op_id") or _if_pending_target(args).get("op_id")
            )
            if target is None or target.get("verb") != "scene.apply":
                return
            # A13: `compensations` es el numero de entregadas; se refresca al
            # llegar el resultado (entregada ya, con o sin resultado util).
            self._compensation_attempts_locked(target)
            if status != "done":
                return
            if not self.valid_read(order, read) or read.get("epoch") != order.get("epoch"):
                return
            if target.get("epoch") != read.get("epoch"):
                return
            st, rsn = _stopped_apply_predicate(target, read, wsize)
            if st in ("parcial", "fallido"):
                self.backend.set_op_state(target["op_id"], st, "servidor", rsn)
                target["bstate"] = "terminal"

    # --- Etapa de actores (F3-offline-2 §4) ----------------------------------

    def _actor_engine_locked(self):
        srv = self.bridge.peers.get("server")
        return srv.get("actor_engine") if isinstance(srv, dict) else None

    def _actor_guard_locked(self, epoch):
        """Guarda comun (§4): None si se puede encolar una orden de actor; si no, el motivo."""
        srv = self.bridge.peers.get("server")
        if not isinstance(srv, dict) or srv.get("lost"):
            return "conexion_perdida"
        if srv.get("epoch") != epoch:
            return "mundo_reiniciado"
        if srv.get("actor_engine") != "expansion":
            return "expansion_unavailable"
        return None

    def _close_apply_ok_locked(self, order, reason):
        """Cierre unico del apply con el predicado cumplido (§4.1): directo o reconciliado."""
        op_id = order["op_id"]
        actor_orders = order.get("actor_orders") or []
        if not actor_orders:
            self.backend.set_op_state(op_id, "observado", "servidor", reason)
            return
        if self.backend.ops[op_id]["state"] != "aplicado":
            self.backend.set_op_state(op_id, "aplicado", "servidor", None)
        guard = self._actor_guard_locked(order.get("epoch"))
        if guard is not None:
            self.backend.set_op_state(op_id, "parcial", "backend", guard)
            return
        stage = {"reason": reason, "lids": {a["a_lid"]: None for a in actor_orders}, "closed": False}
        self._stage[op_id] = stage
        for args in actor_orders:
            ok, internal = self.bridge.enqueue_order("actor.apply", copy.deepcopy(args), internal=True)
            if not ok:
                stage["closed"] = True
                self.backend.set_op_state(op_id, "parcial", "servidor", "actor_error")
                return
            internal["f2"] = True
            internal["purpose"] = "actor_stage"
            internal["parent_op"] = op_id

    def _actor_verdict(self, args, status, read, wsize):
        """§4.2: `ok`, `no_cumple`, `rechazado` o `error` de un `actor.apply`."""
        if status == "rejected":
            return "rechazado"
        if status != "done":
            return "error"
        if not valid_actor_read(read, world_size=wsize) or len(read["actors"]) != 1:
            return "no_cumple"
        row = read["actors"][0]
        if row[0] != args.get("a_lid"):
            return "no_cumple"
        expected = {"cls": args.get("a_cls"), "items": args.get("a_items")}
        if judge_identity(expected, row)["verdict"] != "PASA":
            return "no_cumple"
        dist = math.hypot(row[2] - args.get("a_x_mm"), row[4] - args.get("a_z_mm"))
        if not dist < _ACTOR_POS_TOL_MM:
            return "no_cumple"
        return "ok"

    def _on_actor_stage_result_locked(self, order, status, read, wsize):
        op_id = order.get("parent_op")
        stage = self._stage.get(op_id)
        op = self.backend.ops.get(op_id)
        if stage is None or stage["closed"] or op is None or op["state"] != "aplicado":
            return  # resultado tardio: se acusa y no cambia nada
        args = order.get("args") or {}
        verdict = self._actor_verdict(args, status, read, wsize)
        if verdict != "ok":
            stage["closed"] = True
            self.backend.set_op_state(op_id, "parcial", "servidor", _ACTOR_STAGE_REASON[verdict])
            return
        stage["lids"][args.get("a_lid")] = "ok"
        if all(v == "ok" for v in stage["lids"].values()):
            stage["closed"] = True
            self.backend.set_op_state(op_id, "observado", "servidor", stage["reason"])

    def _close_reset_locked(self, order, st, rsn):
        """Cierre unico del reset de API (§4.3): con motor, `actor.reset` antes del veredicto."""
        op_id = order["op_id"]
        if self._actor_engine_locked() != "expansion":
            self.backend.set_op_state(op_id, st, "servidor", rsn)
            return
        verdict = (st, rsn)
        if self.backend.ops[op_id]["state"] != "aplicado":
            self.backend.set_op_state(op_id, "aplicado", "servidor", None)
        guard = self._actor_guard_locked(order.get("epoch"))
        if guard is not None:
            self._reset_fail_locked(op_id, verdict, guard, "backend")
            return
        args = order.get("args") or {}
        ok, internal = self.bridge.enqueue_order(
            "actor.reset", {"f2": 1, "doc_id": args.get("doc_id")}, internal=True)
        if not ok:
            self._reset_fail_locked(op_id, verdict, "actores_vivos", "servidor")
            return
        internal["f2"] = True
        internal["purpose"] = "actor_reset"
        internal["parent_op"] = op_id
        self._reset_verdict[op_id] = verdict

    def _reset_fail_locked(self, op_id, verdict, reason, origin):
        """§4.3: el motivo de la escena manda; si la escena cumplio, `parcial/<reason>`."""
        st, rsn = verdict
        if st == "observado":
            self.backend.set_op_state(op_id, "parcial", origin, reason)
        else:
            self.backend.set_op_state(op_id, st, "servidor", rsn)

    def _on_actor_reset_result_locked(self, order, status, read, wsize):
        op_id = order.get("parent_op")
        op = self.backend.ops.get(op_id)
        verdict = self._reset_verdict.get(op_id)
        if verdict is None or op is None or op["state"] != "aplicado":
            return
        del self._reset_verdict[op_id]
        if status == "done" and valid_actor_read(read, world_size=wsize) and read["actors"] == []:
            self.backend.set_op_state(op_id, verdict[0], "servidor", verdict[1])
        else:
            self._reset_fail_locked(op_id, verdict, "actores_vivos", "servidor")

    def on_internal_dropped_locked(self, order, reason):
        """§4.4: el bridge descarto una orden interna (conexion, epoch o TTL)."""
        purpose = order.get("purpose")
        if purpose == "actor_observe":
            if self._actor_observe_op_id == order.get("op_id"):
                self._actor_observe_op_id = None
            return
        if purpose not in ("actor_stage", "actor_reset"):
            return
        op_id = order.get("parent_op")
        op = self.backend.ops.get(op_id)
        if op is None or op["state"] != "aplicado":
            return
        if purpose == "actor_stage":
            stage = self._stage.get(op_id)
            if stage is None or stage["closed"]:
                return
            stage["closed"] = True
            self.backend.set_op_state(op_id, "parcial", "backend", reason)
            return
        verdict = self._reset_verdict.pop(op_id, None)
        if verdict is not None:
            self._reset_fail_locked(op_id, verdict, reason, "backend")

    # --- Reconciliacion y compensacion (§4.5) -----------------------------

    def _is_order_unresolved_locked(self, order, epoch=None):
        if not self.is_f2_order(order) or order.get("internal"):
            return False
        if order.get("session") != self.bridge.session:
            return False
        if order.get("bstate") != "parcial":
            return False
        if epoch is not None and order.get("epoch") != epoch:
            return False
        op = self.backend.ops.get(order.get("op_id"))
        if op is None or op.get("state") != "parcial":
            return False
        if op.get("reason") in TERMINAL_PARCIAL_REASONS:
            return False
        return True

    def _unresolved_orders_locked(self, epoch=None):
        if epoch is None:
            srv = self.bridge.peers.get("server")
            if not srv or srv.get("lost") or not srv.get("epoch"):
                return []
            epoch = srv.get("epoch")
        orders = [
            o for o in self.bridge.orders.values()
            if self._is_order_unresolved_locked(o, epoch=epoch)
        ]
        orders.sort(key=lambda o: o.get("_seq", 0))
        return orders

    def _find_unresolved_order_locked(self, op_id):
        if not op_id:
            return None
        order = self.bridge.orders.get((self.bridge.session, op_id))
        if order is not None and self._is_order_unresolved_locked(order, epoch=order.get("epoch")):
            return order
        return None

    def has_unresolved_locked(self):
        """Indica si queda alguna orden F2 de esta sesion en `parcial` sin resolver en el epoch actual (§4.5)."""
        return len(self._unresolved_orders_locked()) > 0

    def _active_internal_reconcile_locked(self):
        srv = self.bridge.peers.get("server")
        if not srv or srv.get("lost"):
            return None
        conn = srv.get("conn")
        for o in self.bridge.orders.values():
            if not o.get("internal") or not self.is_f2_order(o):
                continue
            if o.get("purpose") not in ("reconcile_checkpoint", "compensate"):
                continue
            if o.get("bstate") in ("pendiente", "ejecutando") and o.get("conn") == conn:
                return o
        return None

    def _compensation_attempts_locked(self, order):
        """Compensaciones entregadas de la orden, en orden de encolado (§4.5 / A13).

        Se guarda en la orden objetivo la clave de la interna en `bridge.orders`
        (`(session, op_id)`) junto con su `comp_request_n`. Cuenta si la interna
        tiene `delivered_inst` (la puso la entrega en `bridge.py`), aunque su
        resultado se pierda y termine en `descartada`. `compensations` queda como
        el numero de entregadas.
        """
        delivered = []
        for att in order.get("comp_attempts") or ():
            internal = self.bridge.orders.get((att.get("session"), att.get("op_id")))
            if internal is not None and internal.get("delivered_inst") is not None:
                delivered.append((att, internal))
        order["compensations"] = len(delivered)
        return delivered

    def _mark(self, order, state, reason, origin="servidor", terminal=True):
        self.backend.set_op_state(order["op_id"], state, origin, reason)
        if terminal:
            order["bstate"] = "terminal"

    def on_world_read_locked(self, read):
        """Procesa una lectura del mundo para reconciliar o compensar ordenes F2 (§4.5)."""
        srv = self.bridge.peers.get("server")
        if srv is None or srv.get("lost"):
            return  # A5: solo lecturas que reconcilian
        wsize = self._world_size_locked()
        if not _valid_read_compat(read, world_size=wsize):
            return
        epoch = read.get("epoch")
        if epoch != srv.get("epoch"):
            return  # A5: el epoch manda; una lectura de otro mundo no juzga
        unresolved = self._unresolved_orders_locked(epoch=epoch)
        if not unresolved:
            return

        gen = read.get("generation")
        scene = read["scene"]
        pending = scene.get("pending")
        last = scene.get("last")
        doc_id = scene.get("doc_id")

        for order in unresolved:
            if not self._is_order_unresolved_locked(order, epoch=epoch):
                continue
            order_doc_id = (order.get("args") or {}).get("doc_id")
            if order_doc_id and order_doc_id != doc_id:
                continue

            op_id = order["op_id"]
            sess = order["session"]
            verb = order.get("verb")
            delivered_comps = self._compensation_attempts_locked(order)

            # 1. apply cuya (session, op_id) esta en generation (§4.5)
            if (
                verb == "scene.apply"
                and isinstance(gen, dict)
                and gen.get("session") == sess
                and gen.get("op_id") == op_id
            ):
                args = order.get("args") or {}
                if (
                    gen.get("rev") != args.get("rev")
                    or gen.get("hash") != args.get("hash")
                    or gen.get("plan_sha256") != args.get("plan_sha256")
                ):
                    self._mark(order, "fallido", "lectura_no_cumple")
                    continue
                if self._active_internal_reconcile_locked() is None:
                    ok, internal_order = self.bridge.enqueue_order(
                        "scene.observe",
                        {"f2": 1, "doc_id": order_doc_id or doc_id, "at": "checkpoint"},
                        internal=True,
                    )
                    if ok:
                        internal_order["f2"] = True
                        internal_order["purpose"] = "reconcile_checkpoint"
                        internal_order["target_op_id"] = op_id
                continue

            # 2. apply cuya (session, op_id) esta en scene.pending (§4.5, D8)
            if (
                verb == "scene.apply"
                and isinstance(pending, dict)
                and pending.get("session") == sess
                and pending.get("op_id") == op_id
            ):
                pn = pending.get("n")
                if delivered_comps:
                    _last_att, last_internal = delivered_comps[-1]
                    if last_internal.get("bstate") in ("pendiente", "ejecutando"):
                        # A13: la ultima entregada sigue en vuelo; no se juzga aqui.
                        continue
                    if len(delivered_comps) >= MAX_COMPENSATIONS:
                        # A13: limite de compensaciones; no hay mas intentos.
                        self._mark(order, "parcial", "interrumpida", origin="backend")
                        continue
                    if pn == _last_att.get("comp_request_n"):
                        # A13: sin progreso tras la ultima compensacion entregada,
                        # terminara por resultado, caducidad o descarte.
                        self._mark(order, "parcial", "interrumpida", origin="backend")
                        continue
                if self._active_internal_reconcile_locked() is None:
                    ok, internal_order = self.bridge.enqueue_order(
                        "scene.reset",
                        {
                            "f2": 1,
                            "doc_id": order_doc_id or doc_id,
                            "if_pending": {"session": sess, "op_id": op_id},
                        },
                        internal=True,
                    )
                    if ok:
                        internal_order["f2"] = True
                        internal_order["purpose"] = "compensate"
                        internal_order["target_op_id"] = op_id
                        internal_order["comp_request_n"] = pn
                        order.setdefault("comp_attempts", []).append({
                            "session": internal_order["session"],
                            "op_id": internal_order["op_id"],
                            "comp_request_n": pn,
                        })
                continue

            # 3. apply o reset con scene.last de esa orden
            if (
                isinstance(last, dict)
                and last.get("session") == sess
                and last.get("op_id") == op_id
            ):
                if verb == "scene.apply":
                    if last.get("verb") != "scene.apply":
                        self._mark(order, "fallido", "lectura_no_cumple")  # A4
                        continue
                    st, rsn = _stopped_apply_predicate(order, read, wsize)
                    if st == "unresolved":
                        continue  # pending sigue siendo A; lo trata la rama 2
                    self._mark(order, st, rsn)
                    continue
                if verb == "scene.reset":
                    if last.get("verb") != "scene.reset":
                        self._mark(order, "fallido", "lectura_no_cumple")  # A4
                        continue
                    st, rsn = _reset_predicate(order, read, wsize)
                    order["bstate"] = "terminal"
                    self._close_reset_locked(order, st, "reconciliada" if st == "observado" else rsn)
                    continue

            # 4. A12: orden superada por otra orden de escena posterior de esta sesion
            if isinstance(last, dict) and last.get("session") == self.bridge.session:
                later = self.bridge.orders.get((self.bridge.session, last.get("op_id")))
                if (
                    later is not None
                    and not later.get("internal")
                    and self.is_f2_order(later)
                    and later.get("_seq", 0) > order.get("_seq", 0)
                    and later.get("verb") == last.get("verb")
                ):
                    self._mark(order, "parcial", "superada", origin="servidor")
                    continue

        self.bridge.cond.notify_all()
