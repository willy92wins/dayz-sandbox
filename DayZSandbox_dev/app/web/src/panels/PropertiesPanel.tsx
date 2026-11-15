import React, { useEffect, useRef } from 'react';
import {
  EntityKind,
  JsonSchemaProperty,
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
  releaseFieldLease,
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
};

const EDITABLE_ENTITY_FIELDS = new Set(['cls', 'name', 'x', 'z', 'yaw']);
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

  const currentDocVal = isAmbient
    ? st.doc.ambiente[field]
    : (ent as SceneEntity)[field];

  const isNumeric = propSchema.type === 'number' || propSchema.type === 'integer';
  let parsedValue: unknown = rawDraft;

  if (isNumeric) {
    const normalized = rawDraft.trim().replace(',', '.');
    const num = Number(normalized);
    parsedValue = normalized !== '' && Number.isFinite(num) ? num : rawDraft;
    if (
      typeof parsedValue === 'number' &&
      typeof currentDocVal === 'number' &&
      parsedValue === currentDocVal
    ) {
      clearFieldErrorAndDraft(targetId, field);
      return true;
    }
  } else {
    if (rawDraft === String(currentDocVal ?? '')) {
      clearFieldErrorAndDraft(targetId, field);
      return true;
    }
  }

  if (isAmbient) {
    return commitSceneOps(
      'Cambiar el ambiente',
      [{ name: 'ambient.set', args: { [field]: parsedValue } }],
      { targetId, field, rawValue: rawDraft }
    );
  }

  const entity = ent as SceneEntity;
  if (field === 'x' || field === 'z') {
    const nextX = field === 'x' ? parsedValue : entity.x;
    const nextZ = field === 'z' ? parsedValue : entity.z;
    return commitSceneOps(
      `Mover ${entity.name}`,
      [{ name: 'entity.move', target: entity.id, args: { x: nextX, z: nextZ } }],
      { targetId, field, rawValue: rawDraft }
    );
  }

  if (field === 'cls') {
    const catClasses = st.catalog?.classes?.[entity.kind] ?? [];
    if (typeof parsedValue === 'string' && !catClasses.includes(parsedValue)) {
      clearFieldErrorAndDraft(targetId, field);
      return true;
    }
    return commitSceneOps(
      `Cambiar la clase de ${entity.name}`,
      [{ name: 'entity.set', target: entity.id, args: { cls: parsedValue } }],
      { targetId, field, rawValue: rawDraft }
    );
  }

  if (field === 'name') {
    return commitSceneOps(
      `Cambiar el nombre de ${entity.name}`,
      [{ name: 'entity.set', target: entity.id, args: { name: parsedValue } }],
      { targetId, field, rawValue: rawDraft }
    );
  }

  if (field === 'yaw') {
    return commitSceneOps(
      `Girar ${entity.name}`,
      [{ name: 'entity.set', target: entity.id, args: { yaw: parsedValue } }],
      { targetId, field, rawValue: rawDraft }
    );
  }

  return true;
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
    const isActor = entityForCls?.kind === 'actor';

    const hasOperation = isAmbient
      ? EDITABLE_AMBIENT_FIELDS.has(prop)
      : !isActor && EDITABLE_ENTITY_FIELDS.has(prop);

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

    if (prop === 'cls' && entityForCls) {
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
          onChange={(e) => {
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
          onChange={(e) => setFieldDraft(targetId, prop, e.target.value)}
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

    return (
      <React.Fragment key={prop}>
        <label htmlFor={`f-${prop}`}>{label}</label>
        {control}
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
    const propEntries = Object.entries(branchProps).filter(([prop]) => prop !== 'id');

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
          {ent.kind === 'actor' ? (
            <div className="lock-banner">
              Actores, vestuario y gestos: llegan con F3
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
