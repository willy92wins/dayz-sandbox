#!/usr/bin/env python3
"""Fases reanudables de la partida F2P (R2-06).

Estado en fases.json (carpeta de trabajo): por fase, estado
(ok/fallida/en_curso), horas UTC, entradas (sha256 que la definen) y
salidas (rutas y sha256). Una fase ok con las mismas entradas se salta;
si cambian sus entradas, se repite ella y las que dependen de ella.
La partida es una fase entera: dentro se anota la parte en curso y las
partes cerradas, solo para diagnostico.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PHASES = ("paquete", "subida", "arranque", "partida", "vuelta", "gate")
DEPENDS = {
    "paquete": (),
    "subida": ("paquete",),
    "arranque": ("subida",),
    "partida": ("arranque",),
    "vuelta": ("partida",),
    "gate": ("vuelta",),
}


def _utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(bytes(data)).hexdigest()


class FaseStore:
    def __init__(self, work_root):
        self.work_root = Path(work_root)
        self.path = self.work_root / "fases.json"
        self.data = {"fases": {}, "partida_detalle": {}}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data = loaded
            except (OSError, ValueError):
                pass
        self.data.setdefault("fases", {})
        self.data.setdefault("partida_detalle", {})

    def save(self):
        self.work_root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n",
                       encoding="utf-8", newline="\n")
        tmp.replace(self.path)

    def get(self, fase):
        return dict(self.data["fases"].get(fase) or {})

    def mark(self, fase, estado, *, entradas=None, salidas=None):
        row = self.get(fase)
        row["estado"] = str(estado)
        if estado == "en_curso" and "desde" not in row:
            row["desde"] = _utc()
        if estado in ("ok", "fallida"):
            row["hasta"] = _utc()
        if entradas is not None:
            row["entradas"] = dict(entradas)
        if salidas is not None:
            row["salidas"] = dict(salidas)
        self.data["fases"][fase] = row
        self.save()
        return row

    def mark_part(self, estado, parte):
        det = self.data.setdefault("partida_detalle", {})
        if estado == "en_curso":
            det["parte_en_curso"] = str(parte)
        elif estado == "cerrada":
            cerradas = list(det.get("partes_cerradas") or [])
            if str(parte) not in cerradas:
                cerradas.append(str(parte))
            det["partes_cerradas"] = cerradas
            if det.get("parte_en_curso") == str(parte):
                det["parte_en_curso"] = ""
        self.save()

    def is_current(self, fase, entradas):
        row = self.get(fase)
        return row.get("estado") == "ok" and row.get("entradas") == dict(entradas or {})


def plan_fases(store, entradas_por_fase, *, reanudar=False, desde=None):
    """Fases a ejecutar. Con desde, solo desde esa fase (incluida)."""
    if desde is not None:
        if desde not in PHASES:
            raise ValueError("fase desconocida: %s" % desde)
        return [desde]
    if not reanudar:
        return list(PHASES)
    to_run = []
    invalidated = False
    for fase in PHASES:
        entradas = dict((entradas_por_fase or {}).get(fase) or {})
        if invalidated or not store.is_current(fase, entradas):
            to_run.append(fase)
            invalidated = True
    return to_run


def dependencias_de(fase):
    if fase not in DEPENDS:
        raise ValueError("fase desconocida: %s" % fase)
    out = []
    for otra in PHASES:
        if otra == fase:
            continue
        vistos = set()
        pila = list(DEPENDS[otra])
        depende = False
        while pila:
            cur = pila.pop()
            if cur == fase:
                depende = True
                break
            if cur in vistos:
                continue
            vistos.add(cur)
            pila.extend(DEPENDS.get(cur, ()))
        if depende:
            out.append(otra)
    return out
