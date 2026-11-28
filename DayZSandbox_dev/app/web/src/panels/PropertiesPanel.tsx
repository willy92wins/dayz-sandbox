import React, { useEffect, useRef } from 'react';
import {
  CameraKey,
  EntityKind,
  GestureItem,
  JsonSchemaProperty,
  MarkItem,
  SceneCamera,
  SceneEntity,
  SceneSchemaDoc,
} from '../types';
import { KindGlyph } from '../icons';
import {
  acquireFieldLease,
  clearFieldErrorAndDraft,
  commitSceneOps,
  copySelectedCoordinates,
  deleteSelectedEntities,
  duplicateSelectedEntity,
  getState,
  NO_CHANGE,
  playCamera,
  releaseFieldLease,
  SceneOp,
  setFieldDraft,
  setState,
  useStudioStore,
} from '../store';
import { keyLabel } from '../shortcuts';

const FIELD_LABELS: Record<string, string> = {
  id: 'Id',
  kind: 'Tipo',
  cls: 'Clase',
  name: 'Nombre',
  x: 'X (m)',
  z: 'Z (m)',
  yaw: 'Rumbo (°)',
  fecha: 'Fecha',
  hora: 'Hora',
  nubes: 'Nubes',
  niebla: 'Niebla',
  lluvia: 'Lluvia',
  viento: 'Viento (m/s)',
  wardrobe: 'Vestuario',
  behaviour: 'Comportamiento',
  roam: 'Radio',
};

const EDITABLE_ENTITY_FIELDS = new Set([
  'cls',
  'name',
  'x',
  'z',
  'yaw',
  'wardrobe',
  'behaviour',
  'roam',
]);
const EDITABLE_AMBIENT_FIELDS = new Set([
  'fecha',
  'hora',
  'nubes',
  'niebla',
  'lluvia',
  'viento',
]);

function resolveSchemaRef(
  schema: SceneSchemaDoc | null,
  prop: JsonSchemaProperty | undefined
): JsonSchemaProperty {
  if (!prop) return {};
  if (prop.$ref && prop.$ref.startsWith('#/$defs/') && schema?.$defs) {
    const defName = prop.$ref.slice('#/$defs/'.length);
    const resolved = schema.$defs[defName];
    if (resolved) {
      return { ...resolved, ...prop, $ref: undefined };
    }
  }
  return prop;
}

function getEntityBranchProperties(
  schema: SceneSchemaDoc | null,
  kind: EntityKind
): Record<string, JsonSchemaProperty> {
  if (!schema?.$defs?.entity?.oneOf) {
    return {};
  }
  for (const rawBranch of schema.$defs.entity.oneOf) {
    const branch = resolveSchemaRef(schema, rawBranch);
    const kindProp = branch.properties?.kind;
    if (!kindProp) continue;
    if (
      kindProp.const === kind ||
      (Array.isArray(kindProp.enum) && kindProp.enum.includes(kind))
    ) {
      const out: Record<string, JsonSchemaProperty> = {};
      for (const [k, v] of Object.entries(branch.properties ?? {})) {
        out[k] = resolveSchemaRef(schema, v);
      }
      return out;
    }
  }
  return {};
}

function getAmbientProperties(
  schema: SceneSchemaDoc | null
): Record<string, JsonSchemaProperty> {
  const ambDef = schema?.$defs?.ambiente;
  if (!ambDef?.properties) return {};
  const out: Record<string, JsonSchemaProperty> = {};
  for (const [k, v] of Object.entries(ambDef.properties)) {
    out[k] = resolveSchemaRef(schema, v);
  }
  return out;
}

function formatSchemaValue(val: unknown): string {
  if (val === undefined || val === null) return '';
  if (Array.isArray(val)) return `${val.length} elementos`;
  if (typeof val === 'object') return `${Object.keys(val as object).length} elementos`;
  return String(val);
}

function parseNumericDraft(raw: string): number | null {
  const normalized = raw.trim().replace(',', '.');
  const num = Number(normalized);
  return normalized !== '' && Number.isFinite(num) ? num : null;
}

function copyCameraKey(k: CameraKey): CameraKey {
  return {
    t: k.t,
    x: k.x,
    y: k.y,
    z: k.z,
    yaw: k.yaw,
    pitch: k.pitch,
    fov: k.fov,
    focus: k.focus,
  };
}

function validCameraKeyField(
  keys: CameraKey[],
  idx: number,
  field: keyof CameraKey,
  num: number
): boolean {
  if (!Number.isFinite(num)) return false;
  if (field === 't') {
    if (idx === 0) return num === 0;
    const prev = keys[idx - 1].t;
    const next = keys[idx + 1]?.t;
    if (!(num > prev)) return false;
    if (next !== undefined && !(num < next)) return false;
    return true;
  }
  if (field === 'x' || field === 'z') return num >= 0 && num <= 15360;
  if (field === 'y') return Number.isFinite(num);
  if (field === 'yaw') return num >= -180 && num < 360;
  if (field === 'pitch') return num >= -90 && num <= 90;
  if (field === 'fov') return num > 0 && num < 180;
  if (field === 'focus') return num > 0;
  return false;
}

const KEY_FIELDS: ReadonlyArray<{ field: keyof CameraKey; label: string }> = [
  { field: 't', label: 't (s)' },
  { field: 'x', label: 'X (m)' },
  { field: 'y', label: 'Y (m)' },
  { field: 'z', label: 'Z (m)' },
  { field: 'yaw', label: 'Yaw (°)' },
  { field: 'pitch', label: 'Pitch (°)' },
  { field: 'fov', label: 'FOV (°)' },
  { field: 'focus', label: 'Enfoque (m)' },
];

function gestureWire(
  g: GestureItem
): { emote: string; at: number } | { emote: string; t: number } {
  if (typeof g.at === 'number') return { emote: g.emote, at: g.at };
  return { emote: g.emote, t: typeof g.t === 'number' ? g.t : 0 };
}

function rejectLocalField(targetId: string, field: string, rawValue: string): void {
  const key = `${targetId}:${field}`;
  setState((prev) => ({
    drafts: { ...prev.drafts, [key]: rawValue },
    rejectedDrafts: {
      ...prev.rejectedDrafts,
      [key]: {
        targetId,
        field,
        rawValue,
        code: 'invalid',
        msg: 'Valor no válido',
        pointer: '',
      },
    },
  }));
}

function buildRangeHelp(propSchema: JsonSchemaProperty): string | null {
  const parts: string[] = [];
  if (propSchema.minimum !== undefined) parts.push(`mín. ${propSchema.minimum}`);
  if (propSchema.exclusiveMinimum !== undefined)
    parts.push(`> ${propSchema.exclusiveMinimum}`);
  if (propSchema.maximum !== undefined) parts.push(`máx. ${propSchema.maximum}`);
  if (propSchema.exclusiveMaximum !== undefined)
    parts.push(`< ${propSchema.exclusiveMaximum}`);
  return parts.length > 0 ? parts.join(' · ') : null;
}

export async function confirmFieldValue(
  targetId: string,
  field: string,
  propSchema: JsonSchemaProperty,
  rawDraft: string | undefined
): Promise<boolean> {
  const st = getState();
  if (st.sinBackend || !st.doc) return false;
  if (rawDraft === undefined) return true;

  const isAmbient = targetId === 'ambiente';
  const ent = isAmbient ? null : st.doc.entities.find((e) => e.id === targetId);
  if (!isAmbient && !ent) return true;

  const isNumeric = propSchema.type === 'number' || propSchema.type === 'integer';
  let parsedValue: unknown = rawDraft;
  if (isNumeric) {
    const normalized = rawDraft.trim().replace(',', '.');
    const num = Number(normalized);
    parsedValue = normalized !== '' && Number.isFinite(num) ? num : rawDraft;
  }
  // «Sin cambios» se decide al salir de la fila, con el documento ya releído tras las tandas
  // anteriores: aquí el documento puede ser viejo (revisión de Sol, R2-05).
  const sameAsDoc = (docVal: unknown): boolean =>
    isNumeric
      ? typeof parsedValue === 'number' && typeof docVal === 'number' && parsedValue === docVal
      : rawDraft === String(docVal ?? '');
  const ctx = { targetId, field, rawValue: rawDraft };

  if (isAmbient) {
    return commitSceneOps(
      'Cambiar el ambiente',
      () => {
        const amb = getState().doc?.ambiente;
        if (!amb) return null;
        if (sameAsDoc(amb[field])) return NO_CHANGE;
        return [{ name: 'ambient.set', args: { [field]: parsedValue } }];
      },
      ctx
    );
  }

  const entity = ent as SceneEntity;
  if (field === 'cls') {
    const catClasses = st.catalog?.classes?.[entity.kind] ?? [];
    if (typeof parsedValue === 'string' && !catClasses.includes(parsedValue)) {
      clearFieldErrorAndDraft(targetId, field);
      return true;
    }
  }

  let label: string;
  let makeOps: (cur: SceneEntity) => SceneOp[];
  if (field === 'x' || field === 'z') {
    // La otra coordenada se lee cuando la tanda sale de la fila, ya con el documento releído tras
    // la tanda anterior: si no, X y luego Z perdían X (revisión de Sol, F01).
    label = `Mover ${entity.name}`;
    makeOps = (cur) => [
      {
        name: 'entity.move',
        target: entity.id,
        args: { x: field === 'x' ? parsedValue : cur.x, z: field === 'z' ? parsedValue : cur.z },
      },
    ];
  } else if (field === 'cls') {
    label = `Cambiar la clase de ${entity.name}`;
    makeOps = () => [{ name: 'entity.set', target: entity.id, args: { cls: parsedValue } }];
  } else if (field === 'name') {
    label = `Cambiar el nombre de ${entity.name}`;
    makeOps = () => [{ name: 'entity.set', target: entity.id, args: { name: parsedValue } }];
  } else if (field === 'yaw') {
    label = `Girar ${entity.name}`;
    makeOps = () => [{ name: 'entity.set', target: entity.id, args: { yaw: parsedValue } }];
  } else if (field === 'wardrobe') {
    label = `Cambiar el vestuario de ${entity.name}`;
    makeOps = () => [
      { name: 'entity.set', target: entity.id, args: { wardrobe: parsedValue } },
    ];
  } else if (field === 'behaviour') {
    label = `Cambiar el comportamiento de ${entity.name}`;
    makeOps = () => [
      { name: 'entity.set', target: entity.id, args: { behaviour: parsedValue } },
    ];
  } else if (field === 'roam') {
    if (typeof parsedValue !== 'number' || parsedValue <= 0) {
      rejectLocalField(targetId, field, rawDraft);
      return false;
    }
    label = `Cambiar el radio de ${entity.name}`;
    makeOps = () => [
      { name: 'entity.set', target: entity.id, args: { roam: parsedValue } },
    ];
  } else {
    return true;
  }

  return commitSceneOps(
    label,
    () => {
      const cur = getState().doc?.entities.find((e) => e.id === entity.id);
      // La entidad desapareció mientras esperaba: no queda nada que confirmar (F07 ya retiró su
      // borrador).
      if (!cur) return NO_CHANGE;
      if (sameAsDoc((cur as unknown as Record<string, unknown>)[field])) return NO_CHANGE;
      return makeOps(cur);
    },
    ctx
  );
}

export async function confirmActiveFieldBeforeApply(): Promise<boolean> {
  const st = getState();
  const activeEl = document.activeElement as HTMLElement | null;
  if (activeEl && activeEl.dataset?.field && st.doc) {
    const field = activeEl.dataset.field;
    const selectedEntities = st.selectedIds
      .filter((id) => id !== 'ambiente')
      .map((id) => st.doc!.entities.find((e) => e.id === id))
      .filter((e): e is SceneEntity => Boolean(e));
    const targetId =
      selectedEntities.length === 1 ? selectedEntities[0].id : 'ambiente';
    const key = `${targetId}:${field}`;
    const rawDraft = st.drafts[key];
    if (rawDraft !== undefined) {
      const propSchema =
        targetId === 'ambiente'
          ? getAmbientProperties(st.schema)[field] ?? {}
          : getEntityBranchProperties(st.schema, selectedEntities[0].kind)[field] ?? {};
      const ok = await confirmFieldValue(targetId, field, propSchema, rawDraft);
      if (!ok) return false;
    }
  }
  return Object.keys(getState().rejectedDrafts).length === 0;
}

export function PropertiesPanel() {
  const {
    docInfo,
    doc,
    schema,
    catalog,
    selectedIds,
    drafts,
    rejectedDrafts,
    activeLease,
    sinBackend,
    keymap,
    pendingFocusField,
  } = useStudioStore();

  const escapedKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!pendingFocusField) return;
    const { field } = pendingFocusField;
    setState({ pendingFocusField: null });
    // El panel puede venir de una pestaña oculta: Dockview tarda un poco en volver a colgarlo del
    // DOM, así que se reintenta hasta que el campo exista y tenga el foco (unos 600 ms como mucho).
    let tries = 0;
    const tryFocus = () => {
      const el = document.getElementById(`f-${field}`) as HTMLElement | null;
      if (el && el.isConnected) {
        el.focus();
        if (document.activeElement === el) return;
      }
      tries += 1;
      if (tries < 20) window.setTimeout(tryFocus, 30);
    };
    window.setTimeout(tryFocus, 30);
  }, [pendingFocusField]);

  const renderActorMarksAndGestures = (ent: SceneEntity) => {
    const marks: MarkItem[] = Array.isArray(ent.marks) ? ent.marks : [];
    const gestures: GestureItem[] = Array.isArray(ent.gestures) ? ent.gestures : [];
    const emotes = catalog?.emotes ?? [];
    const noEmotes = emotes.length === 0;

    const marksLeaseGranted =
      activeLease?.targetId === ent.id &&
      activeLease.field === 'marks' &&
      activeLease.status === 'granted';
    const gesturesLeaseGranted =
      activeLease?.targetId === ent.id &&
      activeLease.field === 'gestures' &&
      activeLease.status === 'granted';

    const confirmMarkCoord = (k: number, axis: 'x' | 'z', raw: string) => {
      const field = `mark-${k}-${axis}`;
      const num = parseNumericDraft(raw);
      if (num === null || num < 0 || num > 15360) {
        rejectLocalField(ent.id, field, raw);
        return;
      }
      void commitSceneOps(
        `Editar marca ${k}`,
        () => {
          const cur = getState().doc?.entities.find((e) => e.id === ent.id);
          if (!cur) return NO_CHANGE;
          const list: MarkItem[] = (cur.marks ?? []).map((m) => ({ x: m.x, z: m.z }));
          const idx = k - 1;
          if (idx < 0 || idx >= list.length) return NO_CHANGE;
          if (list[idx][axis] === num) return NO_CHANGE;
          list[idx] = { ...list[idx], [axis]: num };
          return [
            { name: 'entity.marks', target: ent.id, args: { marks: list } },
          ];
        },
        { targetId: ent.id, field, rawValue: raw }
      );
    };

    const addMark = () => {
      if (sinBackend) return;
      void commitSceneOps(`Añadir marca`, () => {
        const cur = getState().doc?.entities.find((e) => e.id === ent.id);
        if (!cur) return NO_CHANGE;
        const list: MarkItem[] = (cur.marks ?? []).map((m) => ({ x: m.x, z: m.z }));
        list.push({ x: cur.x, z: cur.z });
        return [{ name: 'entity.marks', target: ent.id, args: { marks: list } }];
      });
    };

    const removeMark = (k: number) => {
      if (sinBackend) return;
      const usedBy = gestures.findIndex((g) => g.at === k);
      if (usedBy >= 0) return;
      void commitSceneOps(`Quitar marca ${k}`, () => {
        const cur = getState().doc?.entities.find((e) => e.id === ent.id);
        if (!cur) return NO_CHANGE;
        const list: MarkItem[] = (cur.marks ?? []).map((m) => ({ x: m.x, z: m.z }));
        const idx = k - 1;
        if (idx < 0 || idx >= list.length) return NO_CHANGE;
        list.splice(idx, 1);
        const gList = (cur.gestures ?? []).map(gestureWire);
        let gChanged = false;
        const nextG = gList.map((g) => {
          if ('at' in g && g.at > k) {
            gChanged = true;
            return { emote: g.emote, at: g.at - 1 };
          }
          return g;
        });
        const ops: SceneOp[] = [
          { name: 'entity.marks', target: ent.id, args: { marks: list } },
        ];
        if (gChanged) {
          ops.push({ name: 'entity.gestures', target: ent.id, args: { gestures: nextG } });
        }
        return ops;
      });
    };

    const commitGestures = (
      label: string,
      field: string,
      rawValue: string,
      nextList: GestureItem[]
    ) => {
      void commitSceneOps(
        label,
        () => {
          const cur = getState().doc?.entities.find((e) => e.id === ent.id);
          if (!cur) return NO_CHANGE;
          return [
            {
              name: 'entity.gestures',
              target: ent.id,
              args: { gestures: nextList.map(gestureWire) },
            },
          ];
        },
        { targetId: ent.id, field, rawValue }
      );
    };

    const addGesture = () => {
      if (sinBackend || noEmotes) return;
      const first = emotes[0];
      void commitSceneOps(`Añadir gesto`, () => {
        const cur = getState().doc?.entities.find((e) => e.id === ent.id);
        if (!cur) return NO_CHANGE;
        const list = (cur.gestures ?? []).map(gestureWire);
        list.push({ emote: first, t: 0 });
        return [{ name: 'entity.gestures', target: ent.id, args: { gestures: list } }];
      });
    };

    const removeGesture = (gIdx: number) => {
      if (sinBackend) return;
      void commitSceneOps(`Quitar gesto ${gIdx}`, () => {
        const cur = getState().doc?.entities.find((e) => e.id === ent.id);
        if (!cur) return NO_CHANGE;
        const list = (cur.gestures ?? []).map(gestureWire);
        const idx = gIdx - 1;
        if (idx < 0 || idx >= list.length) return NO_CHANGE;
        list.splice(idx, 1);
        return [{ name: 'entity.gestures', target: ent.id, args: { gestures: list } }];
      });
    };

    const changeGestureEmote = (gIdx: number, emote: string) => {
      const curList = gestures.map((g) => ({ ...g }));
      const idx = gIdx - 1;
      if (!curList[idx]) return;
      curList[idx] = { ...gestureWire(curList[idx]), emote };
      commitGestures(`Cambiar gesto ${gIdx}`, `gesture-${gIdx}-emote`, emote, curList);
    };

    const changeGestureWhen = (gIdx: number, when: 'at' | 't') => {
      const curList = gestures.map((g) => ({ ...g }));
      const idx = gIdx - 1;
      const g = curList[idx];
      if (!g) return;
      if (when === 'at') {
        if (marks.length === 0) return;
        curList[idx] = { emote: g.emote, at: 1 };
      } else {
        curList[idx] = { emote: g.emote, t: 0 };
      }
      commitGestures(`Cambiar gesto ${gIdx}`, `gesture-${gIdx}-when`, when, curList);
    };

    const confirmGestureValue = (gIdx: number, raw: string) => {
      const field = `gesture-${gIdx}-value`;
      const g = gestures[gIdx - 1];
      if (!g) return;
      const num = parseNumericDraft(raw);
      const usesAt = typeof g.at === 'number';
      if (usesAt) {
        if (num === null || !Number.isInteger(num) || num < 1 || num > marks.length) {
          rejectLocalField(ent.id, field, raw);
          return;
        }
      } else if (num === null || num < 0) {
        rejectLocalField(ent.id, field, raw);
        return;
      }
      const curList = gestures.map((item) => ({ ...item }));
      if (usesAt) {
        curList[gIdx - 1] = { emote: g.emote, at: num as number };
      } else {
        curList[gIdx - 1] = { emote: g.emote, t: num as number };
      }
      commitGestures(`Cambiar gesto ${gIdx}`, field, raw, curList);
    };

    const markField = (k: number, axis: 'x' | 'z') => {
      const field = `mark-${k}-${axis}`;
      const key = `${ent.id}:${field}`;
      const m = marks[k - 1];
      const docVal = m ? String(m[axis]) : '';
      const display = drafts[key] !== undefined ? drafts[key] : docVal;
      const rejected = rejectedDrafts[key];
      return (
        <>
          <label htmlFor={`f-${field}`}>{`Marca ${k} · ${axis.toUpperCase()}`}</label>
          <input
            id={`f-${field}`}
            type="text"
            inputMode="decimal"
            className="f"
            value={display}
            disabled={sinBackend}
            readOnly={!marksLeaseGranted}
            aria-invalid={rejected ? 'true' : undefined}
            onFocus={() => {
              if (sinBackend) return;
              void acquireFieldLease(ent.id, 'marks');
            }}
            onBlur={() => {
              releaseFieldLease(ent.id, 'marks');
              if (escapedKeyRef.current === key) {
                escapedKeyRef.current = null;
                return;
              }
              if (sinBackend) return;
              const latest = getState().drafts[key];
              if (latest !== undefined) confirmMarkCoord(k, axis, latest);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                escapedKeyRef.current = key;
                clearFieldErrorAndDraft(ent.id, field);
                return;
              }
              if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                e.stopPropagation();
                const latest = getState().drafts[key];
                if (!sinBackend && latest !== undefined) confirmMarkCoord(k, axis, latest);
              }
            }}
            onChange={(e) => {
              if (!marksLeaseGranted) return;
              setFieldDraft(ent.id, field, e.target.value);
            }}
          />
        </>
      );
    };

    return (
      <>
        <div className="psec" data-section="marcas">
          <div className="psec-h">
            <span>Marcas</span>
          </div>
          <div className="pgrid">
            {marks.length === 0 ? <span>Sin marcas</span> : null}
            {marks.map((_, i) => {
              const k = i + 1;
              const usedBy = gestures.findIndex((g) => g.at === k);
              const blocked = usedBy >= 0;
              const note = blocked ? `La usa el gesto ${usedBy + 1}` : null;
              return (
                <React.Fragment key={k}>
                  <div data-mark={k} className="pgrid" style={{ display: 'contents' }}>
                    {markField(k, 'x')}
                    {markField(k, 'z')}
                    <button
                      type="button"
                      className="btn sm"
                      aria-disabled={blocked || sinBackend ? 'true' : undefined}
                      title={note ?? undefined}
                      onClick={() => {
                        if (blocked || sinBackend) return;
                        removeMark(k);
                      }}
                      onKeyDown={(e) => {
                        if ((e.key === 'Enter' || e.key === ' ') && (blocked || sinBackend)) {
                          e.preventDefault();
                          e.stopPropagation();
                        }
                      }}
                    >
                      {`Quitar marca ${k}`}
                    </button>
                    {note ? <span>{note}</span> : null}
                  </div>
                </React.Fragment>
              );
            })}
          </div>
          <div className="prop-actions">
            <button
              type="button"
              className="btn sm"
              disabled={sinBackend}
              onClick={() => addMark()}
            >
              Añadir marca
            </button>
          </div>
        </div>

        <div className="psec" data-section="gestos">
          <div className="psec-h">
            <span>Gestos</span>
          </div>
          <div className="pgrid">
            {gestures.length === 0 ? <span>Sin gestos</span> : null}
            {gestures.map((g, i) => {
              const gIdx = i + 1;
              const when: 'at' | 't' = typeof g.at === 'number' ? 'at' : 't';
              const value = when === 'at' ? String(g.at ?? '') : String(g.t ?? '');
              const valueField = `gesture-${gIdx}-value`;
              const valueKey = `${ent.id}:${valueField}`;
              const display = drafts[valueKey] !== undefined ? drafts[valueKey] : value;
              const rejected = rejectedDrafts[valueKey];
              const emoteInCat = emotes.includes(g.emote);
              return (
                <div key={gIdx} data-gesture={gIdx} className="pgrid" style={{ display: 'contents' }}>
                  <select
                    id={`f-gesture-${gIdx}-emote`}
                    className="f"
                    value={g.emote}
                    disabled={sinBackend}
                    aria-readonly={!gesturesLeaseGranted ? 'true' : undefined}
                    onFocus={() => {
                      if (sinBackend) return;
                      void acquireFieldLease(ent.id, 'gestures');
                    }}
                    onBlur={() => releaseFieldLease(ent.id, 'gestures')}
                    onChange={(e) => {
                      if (!gesturesLeaseGranted) return;
                      changeGestureEmote(gIdx, e.target.value);
                    }}
                  >
                    {!emoteInCat && g.emote ? (
                      <option value={g.emote}>{g.emote}</option>
                    ) : null}
                    {emotes.map((em) => (
                      <option key={em} value={em}>
                        {em}
                      </option>
                    ))}
                  </select>
                  <select
                    id={`f-gesture-${gIdx}-when`}
                    className="f"
                    value={when}
                    disabled={sinBackend}
                    aria-readonly={!gesturesLeaseGranted ? 'true' : undefined}
                    onFocus={() => {
                      if (sinBackend) return;
                      void acquireFieldLease(ent.id, 'gestures');
                    }}
                    onBlur={() => releaseFieldLease(ent.id, 'gestures')}
                    onChange={(e) => {
                      if (!gesturesLeaseGranted) return;
                      const next = e.target.value === 'at' ? 'at' : 't';
                      changeGestureWhen(gIdx, next);
                    }}
                  >
                    <option value="at" disabled={marks.length === 0}>
                      En la marca
                    </option>
                    <option value="t">A los segundos</option>
                  </select>
                  <input
                    id={`f-gesture-${gIdx}-value`}
                    type="text"
                    inputMode="decimal"
                    className="f"
                    value={display}
                    disabled={sinBackend}
                    readOnly={!gesturesLeaseGranted}
                    aria-invalid={rejected ? 'true' : undefined}
                    onFocus={() => {
                      if (sinBackend) return;
                      void acquireFieldLease(ent.id, 'gestures');
                    }}
                    onBlur={() => {
                      releaseFieldLease(ent.id, 'gestures');
                      if (escapedKeyRef.current === valueKey) {
                        escapedKeyRef.current = null;
                        return;
                      }
                      if (sinBackend) return;
                      const latest = getState().drafts[valueKey];
                      if (latest !== undefined) confirmGestureValue(gIdx, latest);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Escape') {
                        e.preventDefault();
                        e.stopPropagation();
                        escapedKeyRef.current = valueKey;
                        clearFieldErrorAndDraft(ent.id, valueField);
                        return;
                      }
                      if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                        e.preventDefault();
                        e.stopPropagation();
                        const latest = getState().drafts[valueKey];
                        if (!sinBackend && latest !== undefined) {
                          confirmGestureValue(gIdx, latest);
                        }
                      }
                    }}
                    onChange={(e) => {
                      if (!gesturesLeaseGranted) return;
                      setFieldDraft(ent.id, valueField, e.target.value);
                    }}
                  />
                  <button
                    type="button"
                    className="btn sm"
                    disabled={sinBackend}
                    onClick={() => removeGesture(gIdx)}
                  >
                    {`Quitar gesto ${gIdx}`}
                  </button>
                </div>
              );
            })}
          </div>
          <div className="prop-actions">
            <button
              type="button"
              className="btn sm"
              aria-disabled={noEmotes || sinBackend ? 'true' : undefined}
              onClick={() => {
                if (noEmotes || sinBackend) return;
                addGesture();
              }}
              onKeyDown={(e) => {
                if ((e.key === 'Enter' || e.key === ' ') && (noEmotes || sinBackend)) {
                  e.preventDefault();
                  e.stopPropagation();
                }
              }}
            >
              Añadir gesto
            </button>
          </div>
        </div>
      </>
    );
  };

  if (!doc || !docInfo) {
    return (
      <div className="panel" data-panel="propiedades">
        <div className="panel-header">
          <span>Propiedades</span>
        </div>
        <div className="panel-body">Cargando…</div>
      </div>
    );
  }

  const selectedEntities = selectedIds
    .filter((id) => id !== 'ambiente')
    .map((id) => doc.entities.find((e) => e.id === id))
    .filter((e): e is SceneEntity => Boolean(e));

  const selectedCameras = selectedIds
    .map((id) => (doc.cameras ?? []).find((c) => c.id === id))
    .filter((c): c is SceneCamera => Boolean(c));

  const renderSchemaField = (
    targetId: string,
    prop: string,
    propSchema: JsonSchemaProperty,
    docValue: unknown,
    entityForCls?: SceneEntity
  ) => {
    const key = `${targetId}:${prop}`;
    const label = FIELD_LABELS[prop] ?? prop;
    const isKnownLabel = Object.prototype.hasOwnProperty.call(FIELD_LABELS, prop);
    const isAmbient = targetId === 'ambiente';
    const hasOperation = isAmbient
      ? EDITABLE_AMBIENT_FIELDS.has(prop)
      : EDITABLE_ENTITY_FIELDS.has(prop);

    const isEditableField =
      isKnownLabel &&
      hasOperation &&
      propSchema.const === undefined &&
      propSchema.type !== 'array' &&
      propSchema.type !== 'object';

    const draftVal = drafts[key];
    const rejected = rejectedDrafts[key];
    const displayValue =
      draftVal !== undefined ? draftVal : formatSchemaValue(docValue);

    const leaseForThisField =
      activeLease &&
      activeLease.targetId === targetId &&
      activeLease.field === prop
        ? activeLease
        : null;

    const leaseGranted = leaseForThisField?.status === 'granted';
    const leaseDeniedReason =
      leaseForThisField?.status === 'denied' ? leaseForThisField.reason : null;

    const minVal = propSchema.minimum ?? propSchema.exclusiveMinimum;
    const maxVal = propSchema.maximum ?? propSchema.exclusiveMaximum;
    const helpText = buildRangeHelp(propSchema);
    const helpId = helpText ? `help-${targetId}-${prop}` : undefined;

    const handleFocus = () => {
      if (!isEditableField || sinBackend) return;
      void acquireFieldLease(targetId, prop);
    };

    const handleBlur = () => {
      if (isEditableField) {
        releaseFieldLease(targetId, prop);
      }
      if (escapedKeyRef.current === key) {
        escapedKeyRef.current = null;
        return;
      }
      if (!isEditableField || sinBackend) return;
      const latestDraft = getState().drafts[key];
      if (latestDraft !== undefined) {
        void confirmFieldValue(targetId, prop, propSchema, latestDraft);
      }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement | HTMLSelectElement>) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        escapedKeyRef.current = key;
        clearFieldErrorAndDraft(targetId, prop);
        return;
      }
      if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        e.stopPropagation();
        const latestDraft = getState().drafts[key];
        if (isEditableField && !sinBackend && latestDraft !== undefined) {
          void confirmFieldValue(targetId, prop, propSchema, latestDraft);
        }
      }
    };

    let control: React.ReactNode;

    if (prop === 'wardrobe' && entityForCls) {
      const catList = catalog?.wardrobes ?? [];
      const curVal = String(docValue ?? '');
      const inCatalog = catList.includes(curVal);
      const selectValue = draftVal !== undefined ? draftVal : curVal;
      control = (
        <select
          id={`f-${prop}`}
          data-field={prop}
          className="f"
          value={selectValue}
          disabled={sinBackend || !isEditableField}
          aria-invalid={rejected ? 'true' : undefined}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          aria-readonly={!leaseGranted ? 'true' : undefined}
          onChange={(e) => {
            if (!leaseGranted) return;
            const nextVal = e.target.value;
            setFieldDraft(targetId, prop, nextVal);
            void confirmFieldValue(targetId, prop, propSchema, nextVal);
          }}
        >
          {!inCatalog && curVal ? (
            <option value={curVal}>{curVal} · no está en el catálogo</option>
          ) : null}
          {catList.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      );
    } else if (prop === 'cls' && entityForCls) {
      const catList = catalog?.classes?.[entityForCls.kind] ?? [];
      const curCls = String(docValue ?? '');
      const inCatalog = catList.includes(curCls);
      const selectValue = draftVal !== undefined ? draftVal : curCls;
      control = (
        <select
          id={`f-${prop}`}
          data-field={prop}
          className="f"
          value={selectValue}
          disabled={sinBackend || !isEditableField}
          aria-invalid={rejected ? 'true' : undefined}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          aria-readonly={!leaseGranted ? 'true' : undefined}
          onChange={(e) => {
            // Un select no tiene readOnly: sin préstamo concedido, el cambio se ignora y el control
            // vuelve al valor del documento (revisión de Sol, F04).
            if (!leaseGranted) return;
            const nextVal = e.target.value;
            setFieldDraft(targetId, prop, nextVal);
            void confirmFieldValue(targetId, prop, propSchema, nextVal);
          }}
        >
          {!inCatalog && curCls ? (
            <option value={curCls}>{curCls} · no está en el catálogo</option>
          ) : null}
          {catList.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      );
    } else if (Array.isArray(propSchema.enum)) {
      control = (
        <select
          id={`f-${prop}`}
          data-field={prop}
          className="f"
          value={displayValue}
          disabled={sinBackend || !isEditableField}
          aria-invalid={rejected ? 'true' : undefined}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          aria-readonly={!leaseGranted ? 'true' : undefined}
          onChange={(e) => {
            if (!leaseGranted) return; // F04: sin préstamo concedido no se edita
            const nextVal = e.target.value;
            setFieldDraft(targetId, prop, nextVal);
            if (prop === 'behaviour') {
              void confirmFieldValue(targetId, prop, propSchema, nextVal);
            }
          }}
        >
          {propSchema.enum.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      );
    } else if (propSchema.type === 'number' || propSchema.type === 'integer') {
      control = (
        <input
          id={`f-${prop}`}
          data-field={prop}
          type="text"
          inputMode="decimal"
          className="f"
          value={displayValue}
          disabled={sinBackend}
          readOnly={!isEditableField || !leaseGranted}
          data-min={minVal !== undefined ? String(minVal) : undefined}
          data-max={maxVal !== undefined ? String(maxVal) : undefined}
          aria-describedby={helpId}
          aria-invalid={rejected ? 'true' : undefined}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          onChange={(e) => {
            if (!isEditableField || !leaseGranted) return;
            setFieldDraft(targetId, prop, e.target.value);
          }}
        />
      );
    } else {
      control = (
        <input
          id={`f-${prop}`}
          data-field={prop}
          type="text"
          className="f"
          value={displayValue}
          disabled={sinBackend}
          readOnly={!isEditableField || !leaseGranted}
          aria-invalid={rejected ? 'true' : undefined}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          onChange={(e) => {
            if (!isEditableField || !leaseGranted) return;
            setFieldDraft(targetId, prop, e.target.value);
          }}
        />
      );
    }

    const wardrobeItems =
      prop === 'wardrobe' && entityForCls
        ? catalog?.wardrobe_items?.[String(entityForCls.wardrobe ?? '')] ?? []
        : null;

    return (
      <React.Fragment key={prop}>
        <label htmlFor={`f-${prop}`}>{label}</label>
        {control}
        {wardrobeItems ? (
          <ul data-wardrobe-items>
            {wardrobeItems.length === 0 ? (
              <li>Sin prendas en el catálogo</li>
            ) : (
              wardrobeItems.map((clsName) => <li key={clsName}>{clsName}</li>)
            )}
          </ul>
        ) : null}
        {helpText ? (
          <div id={helpId} className="field-help">
            {helpText}
          </div>
        ) : null}
        {leaseDeniedReason ? (
          <div className="err-msg" role="status">
            {leaseDeniedReason}
          </div>
        ) : null}
        {rejected ? (
          <div className="err-msg" role="alert">
            {rejected.msg} ({rejected.code} · {rejected.pointer})
          </div>
        ) : null}
      </React.Fragment>
    );
  };

  if (selectedCameras.length === 1 && selectedEntities.length === 0) {
    const cam = selectedCameras[0];
    const keys = Array.isArray(cam.keys) ? cam.keys : [];
    const nameKey = `${cam.id}:name`;
    const nameDraft = drafts[nameKey];
    const nameRejected = rejectedDrafts[nameKey];
    const nameDisplay = nameDraft !== undefined ? nameDraft : cam.name;
    const nameLease =
      activeLease && activeLease.targetId === cam.id && activeLease.field === 'name'
        ? activeLease
        : null;
    const nameGranted = nameLease?.status === 'granted';
    const keysLeaseGranted =
      activeLease?.targetId === cam.id &&
      activeLease.field === 'keys' &&
      activeLease.status === 'granted';

    const confirmCamName = (raw: string) => {
      if (raw.trim() === '') {
        rejectLocalField(cam.id, 'name', raw);
        return;
      }
      void commitSceneOps(
        `Cambiar el nombre de ${cam.name}`,
        () => {
          const cur = (getState().doc?.cameras ?? []).find((c) => c.id === cam.id);
          if (!cur) return NO_CHANGE;
          if (raw === cur.name) return NO_CHANGE;
          return [{ name: 'camera.set', target: cam.id, args: { name: raw } }];
        },
        { targetId: cam.id, field: 'name', rawValue: raw }
      );
    };

    const confirmKeyField = (k: number, field: keyof CameraKey, raw: string) => {
      const draftField = `key-${k}-${field}`;
      const num = parseNumericDraft(raw);
      const idx = k - 1;
      if (num === null || !validCameraKeyField(keys, idx, field, num)) {
        rejectLocalField(cam.id, draftField, raw);
        return;
      }
      void commitSceneOps(
        `Editar clave ${k}`,
        () => {
          const cur = (getState().doc?.cameras ?? []).find((c) => c.id === cam.id);
          if (!cur) return NO_CHANGE;
          const list = (cur.keys ?? []).map(copyCameraKey);
          if (idx < 0 || idx >= list.length) return NO_CHANGE;
          if (list[idx][field] === num) return NO_CHANGE;
          list[idx] = { ...list[idx], [field]: num };
          return [{ name: 'camera.set', target: cam.id, args: { keys: list } }];
        },
        { targetId: cam.id, field: draftField, rawValue: raw }
      );
    };

    const addKey = () => {
      if (sinBackend) return;
      void commitSceneOps('Añadir clave', () => {
        const cur = (getState().doc?.cameras ?? []).find((c) => c.id === cam.id);
        if (!cur || !cur.keys.length) return NO_CHANGE;
        const list = cur.keys.map(copyCameraKey);
        const last = list[list.length - 1];
        list.push({ ...copyCameraKey(last), t: last.t + 1 });
        return [{ name: 'camera.set', target: cam.id, args: { keys: list } }];
      });
    };

    const removeKey = (k: number) => {
      if (sinBackend || keys.length <= 1) return;
      void commitSceneOps(`Quitar clave ${k}`, () => {
        const cur = (getState().doc?.cameras ?? []).find((c) => c.id === cam.id);
        if (!cur || cur.keys.length <= 1) return NO_CHANGE;
        const idx = k - 1;
        if (idx < 0 || idx >= cur.keys.length) return NO_CHANGE;
        const list = cur.keys.map(copyCameraKey);
        list.splice(idx, 1);
        let next = list;
        if (idx === 0 && next.length > 0) {
          const shift = next[0].t;
          next = next.map((item, i) =>
            i === 0 ? { ...item, t: 0 } : { ...item, t: item.t - shift }
          );
        }
        return [{ name: 'camera.set', target: cam.id, args: { keys: next } }];
      });
    };

    const keyInput = (k: number, field: keyof CameraKey, label: string) => {
      const draftField = `key-${k}-${field}`;
      const key = `${cam.id}:${draftField}`;
      const item = keys[k - 1];
      const docVal = item ? String(item[field]) : '';
      const display = drafts[key] !== undefined ? drafts[key] : docVal;
      const rejected = rejectedDrafts[key];
      const tLocked = field === 't' && k === 1;
      return (
        <React.Fragment key={draftField}>
          <label htmlFor={`f-key-${k}-${field}`}>{`Clave ${k} · ${label}`}</label>
          <input
            id={`f-key-${k}-${field}`}
            type="text"
            inputMode="decimal"
            className="f"
            value={display}
            disabled={sinBackend}
            readOnly={tLocked || !keysLeaseGranted}
            aria-invalid={rejected ? 'true' : undefined}
            onFocus={() => {
              if (sinBackend || tLocked) return;
              void acquireFieldLease(cam.id, 'keys');
            }}
            onBlur={() => {
              releaseFieldLease(cam.id, 'keys');
              if (escapedKeyRef.current === key) {
                escapedKeyRef.current = null;
                return;
              }
              if (sinBackend || tLocked) return;
              const latest = getState().drafts[key];
              if (latest !== undefined) confirmKeyField(k, field, latest);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.preventDefault();
                e.stopPropagation();
                escapedKeyRef.current = key;
                clearFieldErrorAndDraft(cam.id, draftField);
                return;
              }
              if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                e.stopPropagation();
                if (tLocked) return;
                const latest = getState().drafts[key];
                if (!sinBackend && latest !== undefined) confirmKeyField(k, field, latest);
              }
            }}
            onChange={(e) => {
              if (tLocked || !keysLeaseGranted) return;
              setFieldDraft(cam.id, draftField, e.target.value);
            }}
          />
        </React.Fragment>
      );
    };

    return (
      <div className="panel" data-panel="propiedades">
        <div className="panel-header">
          <span>Propiedades · {cam.name}</span>
        </div>
        <div className="panel-body">
          {sinBackend ? (
            <div className="lock-banner">
              Sin conexión con el backend: no se puede editar
            </div>
          ) : null}
          <div className="psec">
            <div className="psec-h">
              <span>{cam.name}</span>
            </div>
            <div className="pgrid">
              <label htmlFor="f-cam-name">Nombre</label>
              <input
                id="f-cam-name"
                type="text"
                className="f"
                value={nameDisplay}
                disabled={sinBackend}
                readOnly={!nameGranted}
                aria-invalid={nameRejected ? 'true' : undefined}
                onFocus={() => {
                  if (sinBackend) return;
                  void acquireFieldLease(cam.id, 'name');
                }}
                onBlur={() => {
                  releaseFieldLease(cam.id, 'name');
                  if (escapedKeyRef.current === nameKey) {
                    escapedKeyRef.current = null;
                    return;
                  }
                  if (sinBackend) return;
                  const latest = getState().drafts[nameKey];
                  if (latest !== undefined) confirmCamName(latest);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation();
                    escapedKeyRef.current = nameKey;
                    clearFieldErrorAndDraft(cam.id, 'name');
                    return;
                  }
                  if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                    e.preventDefault();
                    e.stopPropagation();
                    const latest = getState().drafts[nameKey];
                    if (!sinBackend && latest !== undefined) confirmCamName(latest);
                  }
                }}
                onChange={(e) => {
                  if (!nameGranted) return;
                  setFieldDraft(cam.id, 'name', e.target.value);
                }}
              />
            </div>
            <div className="prop-actions">
              <button
                type="button"
                className="btn sm danger"
                id="cam-delete"
                disabled={sinBackend}
                onClick={() => {
                  setState({ selectedIds: [] });
                  void commitSceneOps(`Borrar ${cam.name}`, [
                    { name: 'camera.delete', target: cam.id, args: {} },
                  ]);
                }}
              >
                Borrar cámara
              </button>
            </div>
          </div>

          <div className="psec" data-section="claves">
            <div className="psec-h">
              <span>Claves</span>
            </div>
            {keys.map((_, i) => {
              const k = i + 1;
              return (
                <div key={k} data-key={String(k)}>
                  <div className="pgrid">
                    {KEY_FIELDS.map(({ field, label }) => keyInput(k, field, label))}
                  </div>
                  <div className="prop-actions">
                    <button
                      type="button"
                      className="btn sm"
                      data-key-goto={String(k)}
                      disabled={sinBackend}
                      onClick={() => {
                        void playCamera(cam.id, k - 1);
                      }}
                    >
                      Ir a esta pose
                    </button>
                    <button
                      type="button"
                      className="btn sm danger"
                      data-key-del={String(k)}
                      disabled={sinBackend || keys.length <= 1}
                      onClick={() => removeKey(k)}
                    >
                      {`Quitar clave ${k}`}
                    </button>
                  </div>
                </div>
              );
            })}
            <div className="prop-actions">
              <button
                type="button"
                className="btn sm"
                id="cam-key-add"
                disabled={sinBackend}
                onClick={addKey}
              >
                Añadir clave
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Multi-selection view (§5.2)
  if (selectedEntities.length > 1) {
    const countsByKind: Record<EntityKind, number> = {
      objeto: 0,
      infectado: 0,
      animal: 0,
      actor: 0,
    };
    for (const e of selectedEntities) {
      countsByKind[e.kind] = (countsByKind[e.kind] || 0) + 1;
    }
    return (
      <div className="panel" data-panel="propiedades">
        <div className="panel-header">
          <span>Propiedades · {selectedEntities.length} seleccionadas</span>
        </div>
        <div className="panel-body">
          {sinBackend ? (
            <div className="lock-banner">
              Sin conexión con el backend: no se puede editar
            </div>
          ) : null}
          <div className="psec">
            <div className="psec-h">
              <span>{selectedEntities.length} seleccionadas</span>
            </div>
            <div className="pgrid">
              <span>Objetos</span>
              <span>{countsByKind.objeto}</span>
              <span>Infectados</span>
              <span>{countsByKind.infectado}</span>
              <span>Animales</span>
              <span>{countsByKind.animal}</span>
              <span>Actores</span>
              <span>{countsByKind.actor}</span>
            </div>
            <div className="prop-actions">
              <button
                type="button"
                className="btn danger"
                disabled={sinBackend}
                onClick={() => void deleteSelectedEntities()}
              >
                Borrar <kbd>{keyLabel(keymap.borrar)}</kbd>
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Single entity selected view (§5.2)
  if (selectedEntities.length === 1) {
    const ent = selectedEntities[0];
    const branchProps = getEntityBranchProperties(schema, ent.kind);
    const propEntries = Object.entries(branchProps).filter(
      ([prop]) => prop !== 'id' && prop !== 'marks' && prop !== 'gestures'
    );

    return (
      <div className="panel" data-panel="propiedades">
        <div className="panel-header">
          <span className="psec-h-title">
            <KindGlyph kind={ent.kind} cls={ent.cls} />
            <span>Propiedades · {ent.name}</span>
          </span>
        </div>
        <div className="panel-body">
          {sinBackend ? (
            <div className="lock-banner">
              Sin conexión con el backend: no se puede editar
            </div>
          ) : null}
          <div className="psec">
            <div className="psec-h">
              <span className="psec-h-title">
                <KindGlyph kind={ent.kind} cls={ent.cls} />
                <span>{ent.name}</span>
              </span>
            </div>
            <div className="pgrid">
              {propEntries.map(([prop, propSchema]) =>
                renderSchemaField(ent.id, prop, propSchema, ent[prop], ent)
              )}
            </div>
            <div className="prop-actions">
              <button
                type="button"
                className="btn sm"
                disabled={sinBackend || ent.kind === 'actor'}
                onClick={() => void duplicateSelectedEntity()}
              >
                Duplicar <kbd>{keyLabel(keymap.duplicar)}</kbd>
              </button>
              <button
                type="button"
                className="btn sm"
                onClick={() => copySelectedCoordinates()}
              >
                Copiar coordenadas <kbd>{keyLabel(keymap['copiar-coordenadas'])}</kbd>
              </button>
              <button
                type="button"
                className="btn sm danger"
                disabled={sinBackend}
                onClick={() => void deleteSelectedEntities()}
              >
                Borrar <kbd>{keyLabel(keymap.borrar)}</kbd>
              </button>
            </div>
          </div>

          {ent.kind === 'actor'
            ? renderActorMarksAndGestures(ent)
            : null}

          <details className="tech">
            <summary>Detalles técnicos</summary>
            <div className="tech-id">
              <label htmlFor="f-id">Id</label>
              <input
                id="f-id"
                data-field="id"
                type="text"
                className="f"
                value={ent.id}
                readOnly
                disabled={sinBackend}
              />
            </div>
            <div className="kv">
              <span>doc_id</span>
              <span>{docInfo.doc_id}</span>
              <span>rev</span>
              <span>{docInfo.rev}</span>
              <span>hash</span>
              <span>{docInfo.hash}</span>
            </div>
          </details>
        </div>
      </div>
    );
  }

  // Default: Scene & Ambiente view (§5.2)
  const ambProps = getAmbientProperties(schema);
  const ambEntries = Object.entries(ambProps);
  const counts: Record<EntityKind, number> = {
    objeto: doc.entities.filter((e) => e.kind === 'objeto').length,
    infectado: doc.entities.filter((e) => e.kind === 'infectado').length,
    animal: doc.entities.filter((e) => e.kind === 'animal').length,
    actor: doc.entities.filter((e) => e.kind === 'actor').length,
  };

  return (
    <div className="panel" data-panel="propiedades">
      <div className="panel-header">
        <span className="psec-h-title">
          <KindGlyph kind="ambiente" />
          <span>Propiedades · Escena y Ambiente</span>
        </span>
      </div>
      <div className="panel-body">
        {sinBackend ? (
          <div className="lock-banner">
            Sin conexión con el backend: no se puede editar
          </div>
        ) : null}

        <div className="psec">
          <div className="psec-h">
            <span>Escena</span>
          </div>
          <div className="pgrid">
            <label htmlFor="f-scene-name">Nombre</label>
            <input
              id="f-scene-name"
              type="text"
              className="f"
              value={doc.name}
              readOnly
              disabled={sinBackend}
            />
            <span>Contenido</span>
            <span>
              {counts.objeto} objetos · {counts.infectado} infectados · {counts.animal}{' '}
              animales · {counts.actor} actores
            </span>
          </div>
        </div>

        <div className="psec">
          <div className="psec-h">
            <span className="psec-h-title">
              <KindGlyph kind="ambiente" />
              <span>Ambiente</span>
            </span>
          </div>
          <div className="pgrid">
            {ambEntries.map(([prop, propSchema]) =>
              renderSchemaField('ambiente', prop, propSchema, doc.ambiente[prop])
            )}
          </div>
        </div>

        <details className="tech">
          <summary>Detalles técnicos</summary>
          <div className="kv">
            <span>doc_id</span>
            <span>{docInfo.doc_id}</span>
            <span>rev</span>
            <span>{docInfo.rev}</span>
            <span>hash</span>
            <span>{docInfo.hash}</span>
          </div>
        </details>
      </div>
    </div>
  );
}
