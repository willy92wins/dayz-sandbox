import { useSyncExternalStore } from 'react';
import { DockviewApi } from 'dockview-react';
import {
  Anchor,
  ApplyErrorInfo,
  CatalogResponse,
  EntityKind,
  ModeName,
  NoticeItem,
  OpData,
  ProfilePayload,
  QueueRow,
  RejectedDraft,
  SceneDoc,
  SceneEntity,
  SceneSchemaDoc,
  StudioPanelId,
  ValidationErrorItem,
} from './types';
import { getDefaultKeymap, sanitizeKeymap } from './shortcuts';
import {
  applyFactoryLayoutForMode,
  applyPropsLeftLayoutForMode,
  openOrFocusPanel,
   validateAndSanitizeLayout,
} from './layout';

export const STATE_LABELS: Record<string, string> = {
  pendiente: 'Pendiente',
  ejecutando: 'Ejecutando',
  aplicado: 'Aplicado',
  observado: 'Observado',
  fallido: 'Fallido',
  parcial: 'Parcial',
};

export function isKnownState(state: string): boolean {
  return Object.prototype.hasOwnProperty.call(STATE_LABELS, state);
}

export function stateLabel(state: string): string {
  return isKnownState(state) ? STATE_LABELS[state] : `Desconocido (${state})`;
}

function makeAnchor(op: OpData, source: 'snapshot' | 'op.state', existing?: QueueRow): Anchor {
  const perf = performance.now();
  const atMs = typeof op.at_ms === 'number' ? op.at_ms : 0;
  if (existing && existing.anchor.atMs === atMs) {
    if (source === 'snapshot' && typeof op.age_ms === 'number') {
      const displayed =
        existing.anchor.unknown || existing.anchor.ageMs === null
          ? null
          : existing.anchor.ageMs + (perf - existing.anchor.perfMs);
      if (displayed === null || op.age_ms > displayed) {
        return { atMs, ageMs: op.age_ms, perfMs: perf, unknown: false };
      }
    }
    return existing.anchor;
  }
  if (source === 'snapshot' && typeof op.age_ms === 'number') {
    return { atMs, ageMs: op.age_ms, perfMs: perf, unknown: false };
  }
  const nowWall = Date.now();
  if (atMs - nowWall > 2000) {
    return { atMs, ageMs: null, perfMs: perf, unknown: true };
  }
  return { atMs, ageMs: Math.max(0, nowWall - atMs), perfMs: perf, unknown: false };
}

function rowFromOp(op: OpData, source: 'snapshot' | 'op.state', existing?: QueueRow): QueueRow {
  return {
    op_id: op.op_id,
    state: op.state,
    rev: op.rev,
    hash: op.hash,
    at_ms: op.at_ms,
    origin: op.origin,
    reason: op.reason !== undefined ? op.reason : existing?.reason ?? null,
    verb: op.verb !== undefined ? op.verb : existing?.verb ?? null,
    anchor: makeAnchor(op, source, existing),
  };
}

export function displayedAgeMs(row: QueueRow): number | null {
  if (row.anchor.unknown || row.anchor.ageMs === null) return null;
  return row.anchor.ageMs + (performance.now() - row.anchor.perfMs);
}

export function formatAge(row: QueueRow): string {
  const age = displayedAgeMs(row);
  if (age === null) return 'Edad desconocida';
  const totalSec = Math.floor(age / 1000);
  if (totalSec <= 59) return `${totalSec} s`;
  const totalMin = Math.floor(age / 60000);
  if (totalMin <= 59) return `${totalMin} min`;
  return `${Math.floor(age / 3600000)} h`;
}

export function opNumber(opId: string): number {
  const m = /^op-(\d+)$/.exec(opId);
  return m ? parseInt(m[1], 10) : -1;
}

export interface ActiveLeaseState {
  targetId: string;
  field: string;
  leaseId: string | null;
  status: 'pending' | 'granted' | 'denied';
  reason?: string;
}

export interface StudioState {
  view: 'checking' | 'login' | 'studio';
  loginMessage: string | null;
  connected: boolean;
  sinBackend: boolean;
  lastEventPerfMs: number;
  lastCommitPerfMs: number | null;
  docInfo: { doc_id: string; rev: number; hash: string } | null;
  doc: SceneDoc | null;
  rows: QueueRow[];
  activityFilter: 'todas' | 'en-curso' | 'fallos';
  catalog: CatalogResponse | null;
  schema: SceneSchemaDoc | null;
  mode: ModeName;
  layouts: {
    escena: Record<string, unknown> | null;
    rodaje: Record<string, unknown> | null;
  };
  keymap: Record<string, string | null>;
  profileLoaded: boolean;
  selectedIds: string[];
  hierarchyQuery: string;
  addCategory: EntityKind;
  addQuery: string;
  previewItem: { kind: EntityKind; cls: string } | null;
  placingItem: { kind: EntityKind; cls: string } | null;
  drafts: Record<string, string>;
  rejectedDrafts: Record<string, RejectedDraft>;
  validationErrors: ValidationErrorItem[];
  activeLease: ActiveLeaseState | null;
  applying: boolean;
  removing: boolean;
  applyError: ApplyErrorInfo | null;
  notice: NoticeItem | null;
  flash: string | null;
  shortcutsOpen: boolean;
  toolsMenuOpen: boolean;
  pendingFocusField: { targetId: string; field: string } | null;
  tick: number;
}

let state: StudioState = {
  view: 'checking',
  loginMessage: null,
  connected: false,
  sinBackend: false,
  lastEventPerfMs: performance.now(),
  lastCommitPerfMs: null,
  docInfo: null,
  doc: null,
  rows: [],
  activityFilter: 'todas',
  catalog: null,
  schema: null,
  mode: 'escena',
  layouts: { escena: null, rodaje: null },
  keymap: getDefaultKeymap(),
  profileLoaded: false,
  selectedIds: [],
  hierarchyQuery: '',
  addCategory: 'objeto',
  addQuery: '',
  previewItem: null,
  placingItem: null,
  drafts: {},
  rejectedDrafts: {},
  validationErrors: [],
  activeLease: null,
  applying: false,
  removing: false,
  applyError: null,
  notice: null,
  flash: null,
  shortcutsOpen: false,
  toolsMenuOpen: false,
  pendingFocusField: null,
  tick: 0,
};

const listeners = new Set<() => void>();

function emitChange() {
  for (const listener of listeners) {
    listener();
  }
}

export function setState(patch: Partial<StudioState> | ((prev: StudioState) => Partial<StudioState>)) {
  const nextPatch = typeof patch === 'function' ? patch(state) : patch;
  state = { ...state, ...nextPatch };
  emitChange();
}

export function getState(): StudioState {
  return state;
}

export function setFlash(message: string | null) {
  setState({ flash: message });
}

export function resetStudioState() {
  resetCommitQueue();
  state = {
    view: 'studio',
    loginMessage: null,
    connected: false,
    sinBackend: false,
    lastEventPerfMs: performance.now(),
    lastCommitPerfMs: null,
    docInfo: null,
    doc: null,
    rows: [],
    activityFilter: 'todas',
    catalog: null,
    schema: null,
    mode: 'escena',
    layouts: { escena: null, rodaje: null },
    keymap: getDefaultKeymap(),
    profileLoaded: false,
    selectedIds: [],
    hierarchyQuery: '',
    addCategory: 'objeto',
    addQuery: '',
    previewItem: null,
    placingItem: null,
    drafts: {},
    rejectedDrafts: {},
    validationErrors: [],
    activeLease: null,
    applying: false,
    removing: false,
    applyError: null,
    notice: null,
    flash: null,
    shortcutsOpen: false,
    toolsMenuOpen: false,
    pendingFocusField: null,
    tick: 0,
  };
  emitChange();
}

export function subscribeStore(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useStudioStore(): StudioState {
  return useSyncExternalStore(subscribeStore, getState);
}

// Dockview reference & layout guard
let dockApiRef: DockviewApi | null = null;
let suppressLayoutSave = false;
let layoutDebounceTimer: number | null = null;
let profileInFlight = false;
let profileQueued = false;
let reqCounter = 0;

export function nextRequestId(prefix = 'req'): string {
  reqCounter += 1;
  return `${prefix}-${Date.now()}-${reqCounter}`;
}

export function setDockviewApi(api: DockviewApi | null) {
  dockApiRef = api;
}

export function getDockviewApi(): DockviewApi | null {
  return dockApiRef;
}

export function applyLayoutToDockview(
  api: DockviewApi,
  mode: ModeName,
  savedLayout: Record<string, unknown> | null
) {
  suppressLayoutSave = true;
  try {
    if (savedLayout !== null) {
      const sanitized = validateAndSanitizeLayout(savedLayout, mode);
      if (!sanitized) {
        applyFactoryLayoutForMode(api, mode);
        setState({
          notice: {
            kind: 'layout-incompatible',
            message:
              'El layout guardado no es compatible con esta versión: se ha cargado el de fábrica.',
          },
        });
      } else {
        try {
          api.fromJSON(sanitized);
        } catch {
          applyFactoryLayoutForMode(api, mode);
          setState({
            notice: {
              kind: 'layout-incompatible',
              message:
                'El layout guardado no es compatible con esta versión: se ha cargado el de fábrica.',
            },
          });
        }
      }
    } else {
      applyFactoryLayoutForMode(api, mode);
    }
  } finally {
    window.setTimeout(() => {
      suppressLayoutSave = false;
    }, 50);
  }
}

export function handleDockviewLayoutChange() {
  if (suppressLayoutSave || !dockApiRef || !state.profileLoaded || state.view !== 'studio') {
    return;
  }
  try {
    const raw = dockApiRef.toJSON() as unknown as Record<string, unknown>;
    if (!raw || typeof raw !== 'object' || !raw.panels || Object.keys(raw.panels as object).length === 0) {
      return;
    }
    setState((prev) => ({
      layouts: {
        ...prev.layouts,
        [prev.mode]: raw,
      },
    }));
    scheduleProfileSave(true);
  } catch {
    // Ignore transient serialization issues
  }
}

export function scheduleProfileSave(debounced = false) {
  if (!state.profileLoaded || state.view !== 'studio') return;
  if (layoutDebounceTimer !== null) {
    window.clearTimeout(layoutDebounceTimer);
    layoutDebounceTimer = null;
  }
  if (profileInFlight) {
    profileQueued = true;
    return;
  }
  if (debounced) {
    layoutDebounceTimer = window.setTimeout(() => {
      layoutDebounceTimer = null;
      void flushProfileSave();
    }, 500);
  } else {
    void flushProfileSave();
  }
}

async function flushProfileSave(): Promise<void> {
  if (state.view !== 'studio') return;
  if (layoutDebounceTimer !== null) {
    window.clearTimeout(layoutDebounceTimer);
    layoutDebounceTimer = null;
  }
  if (profileInFlight) {
    profileQueued = true;
    return;
  }
  profileInFlight = true;
  profileQueued = false;

  const payload: ProfilePayload = {
    v: 1,
    layouts: {
      escena: state.layouts.escena,
      rodaje: state.layouts.rodaje,
    },
    keymap: { ...state.keymap },
  };

  try {
    const res = await fetch('/api/profile', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
      },
      body: JSON.stringify(payload),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as { ok?: boolean; code?: string } | null;
    if (res.status === 401 || (res.status === 403 && data?.code === 'csrf_failed')) {
      handleSessionExpired();
      return;
    }
    if (!res.ok) {
      setState({
        notice: {
          kind: 'perfil-no-guardado',
          message: 'No se pudo guardar el perfil',
        },
      });
    }
  } catch {
    markBackendDown();
    setState({
      notice: {
        kind: 'perfil-no-guardado',
        message: 'No se pudo guardar el perfil',
      },
    });
  } finally {
    profileInFlight = false;
    if (profileQueued && state.view === 'studio') {
      profileQueued = false;
      void flushProfileSave();
    }
  }
}

export function handleSessionExpired() {
  // Nada de lo que quede en la fila sale ya: era de esta sesión (revisión de Sol, SEG-01).
  resetCommitQueue();
  releaseActiveLeaseOnUnmount();
  setState({
    view: 'login',
    connected: false,
    loginMessage: 'Sesión caducada: vuelve a entrar',
  });
}

export function markBackendAlive() {
  const patch: Partial<StudioState> = {
    lastEventPerfMs: performance.now(),
  };
  if (state.sinBackend) {
    patch.sinBackend = false;
    if (state.notice?.kind === 'sin-backend') {
      patch.notice = null;
    }
  }
  setState(patch);
}

export function markBackendDown() {
  if (!state.sinBackend) {
    setState({
      sinBackend: true,
      placingItem: null,
      notice: {
        kind: 'sin-backend',
        message: 'Sin conexión con el backend: no se puede guardar ningún cambio.',
      },
    });
  }
}

export async function loadInitialStudioData(): Promise<void> {
  try {
    const [schemaRes, catalogRes, profileRes] = await Promise.all([
      fetch('/api/schema', { credentials: 'same-origin' }),
      fetch('/api/catalog', { credentials: 'same-origin' }),
      fetch('/api/profile', { credentials: 'same-origin' }),
    ]);
    if (
      schemaRes.status === 401 ||
      catalogRes.status === 401 ||
      profileRes.status === 401
    ) {
      handleSessionExpired();
      return;
    }
    markBackendAlive();

    const schemaData =
      schemaRes.status === 200
        ? ((await schemaRes.json().catch(() => null)) as SceneSchemaDoc | null)
        : null;
    const catalogData =
      catalogRes.status === 200
        ? ((await catalogRes.json().catch(() => null)) as CatalogResponse | null)
        : null;
    const profileWrap =
      profileRes.status === 200
        ? ((await profileRes.json().catch(() => null)) as {
            ok: boolean;
            profile: ProfilePayload | null;
            corrupt: boolean;
          } | null)
        : null;

    let nextLayouts: StudioState['layouts'] = { escena: null, rodaje: null };
    let nextKeymap = getDefaultKeymap();
    let nextNotice: NoticeItem | null = state.notice;

    if (profileWrap?.corrupt) {
      nextNotice = {
        kind: 'perfil-corrupto',
        message:
          'El perfil guardado está dañado: se han cargado el layout de fábrica y los atajos de serie.',
      };
    } else if (profileWrap?.profile) {
      const p = profileWrap.profile;
      nextLayouts = {
        escena: p.layouts?.escena ?? null,
        rodaje: p.layouts?.rodaje ?? null,
      };
      const { keymap: sanitizedKm, corrected } = sanitizeKeymap(p.keymap);
      nextKeymap = sanitizedKm;
      if (corrected) {
        nextNotice = {
          kind: 'atajos-corregidos',
          message:
            'Algunos atajos guardados no eran válidos y han vuelto a sus teclas de serie.',
        };
      }
    }

    const firstObjCls = catalogData?.classes?.objeto?.[0] ?? null;

    setState({
      schema: schemaData,
      catalog: catalogData,
      layouts: nextLayouts,
      keymap: nextKeymap,
      profileLoaded: true,
      notice: nextNotice,
      previewItem: firstObjCls ? { kind: 'objeto', cls: firstObjCls } : null,
    });

    if (dockApiRef && (nextLayouts[state.mode] !== null || dockApiRef.panels.length === 0)) {
      applyLayoutToDockview(dockApiRef, state.mode, nextLayouts[state.mode]);
    }
  } catch {
    markBackendDown();
  }
}

let pendingCreatedEntityId: string | null = null;

function isUsableSceneDoc(doc: unknown): doc is SceneDoc {
  return (
    typeof doc === 'object' &&
    doc !== null &&
    Array.isArray((doc as SceneDoc).entities) &&
    typeof (doc as SceneDoc).ambiente === 'object' &&
    (doc as SceneDoc).ambiente !== null
  );
}

export function applyIncomingSceneDoc(
  doc_id: string,
  rev: number,
  hash: string,
  doc: SceneDoc,
  isCommitEvent = false
) {
  setState((prev) => {
    if (prev.docInfo && rev < prev.docInfo.rev) {
      return {};
    }
    const usable = isUsableSceneDoc(doc);
    const patch: Partial<StudioState> = {
      docInfo: { doc_id, rev, hash },
      lastEventPerfMs: performance.now(),
    };
    if (usable) {
      patch.doc = doc;
      // Una entidad que ya no está no puede dejar un borrador que bloquee «Aplicar» para siempre:
      // se retiran sus borradores y su fila de Validación se queda, con «Ya no existe» (Sol, F07).
      const alive = new Set(doc.entities.map((e) => e.id));
      const gone = (key: string) => {
        const target = key.slice(0, key.lastIndexOf(':'));
        return target !== 'ambiente' && !alive.has(target);
      };
      if (Object.keys(prev.drafts).some(gone) || Object.keys(prev.rejectedDrafts).some(gone)) {
        // La generación sube también aquí: una respuesta tardía de esa entidad no puede resucitar
        // sus borradores (revisión de Sol, R2-03).
        for (const k of new Set([...Object.keys(prev.drafts), ...Object.keys(prev.rejectedDrafts)])) {
          if (gone(k)) bumpDraftGen(k);
        }
        patch.drafts = Object.fromEntries(Object.entries(prev.drafts).filter(([k]) => !gone(k)));
        patch.rejectedDrafts = Object.fromEntries(
          Object.entries(prev.rejectedDrafts).filter(([k]) => !gone(k))
        );
      }
    }
    if (isCommitEvent) {
      patch.lastCommitPerfMs = performance.now();
    }
    if (
      usable &&
      pendingCreatedEntityId &&
      doc.entities.some((e) => e.id === pendingCreatedEntityId)
    ) {
      const createdId = pendingCreatedEntityId;
      pendingCreatedEntityId = null;
      patch.selectedIds = [createdId];
      patch.pendingFocusField = { targetId: createdId, field: 'x' };
      if (dockApiRef) {
        openOrFocusPanel(dockApiRef, prev.mode, 'propiedades');
      }
    }
    return patch;
  });
}

// Devuelve si llegó un documento: la fila de commitSceneOps no construye la tanda siguiente sobre una
// lectura fallida (revisión de Sol, R2-01).
export async function fetchAuthoritativeScene(markCommit: boolean): Promise<boolean> {
  try {
    const { res, data } = await fetchJsonWithTimeout('/api/scene', { credentials: 'same-origin' });
    if (res.status === 401) {
      handleSessionExpired();
      return false;
    }
    markBackendAlive();
    if (!res.ok || !data) return false;
    const snap = data as {
      doc_id: string;
      rev: number;
      hash: string;
      doc: SceneDoc;
    };
    applyIncomingSceneDoc(snap.doc_id, snap.rev, snap.hash, snap.doc, markCommit);
    return true;
  } catch {
    markBackendDown();
    return false;
  }
}

export function handleSnapshotEvent(data: {
  doc_id: string;
  rev: number;
  hash: string;
  doc: SceneDoc;
  ops: OpData[];
}) {
  markBackendAlive();
  const byId = new Map(state.rows.map((r) => [r.op_id, r]));
  const nextRows = (data.ops || []).map((op) => rowFromOp(op, 'snapshot', byId.get(op.op_id)));
  setState({ rows: nextRows });
  applyIncomingSceneDoc(data.doc_id, data.rev, data.hash, data.doc, false);
}

export function handleOpStateEvent(op: OpData) {
  markBackendAlive();
  setState((prev) => {
    const existing = prev.rows.find((r) => r.op_id === op.op_id);
    const row = rowFromOp(op, 'op.state', existing);
    const nextRows = existing
      ? prev.rows.map((r) => (r.op_id === op.op_id ? row : r))
      : [...prev.rows, row];
    return { rows: nextRows };
  });
}

// Leases (§5.2)
let leaseRenewTimer: number | null = null;
let leaseSeq = 0;

function clearLeaseTimer() {
  if (leaseRenewTimer !== null) {
    window.clearInterval(leaseRenewTimer);
    leaseRenewTimer = null;
  }
}

export function releaseActiveLeaseOnUnmount() {
  clearLeaseTimer();
  const cur = state.activeLease;
  if (!cur) return;
  const lid = cur.leaseId;
  setState({ activeLease: null });
  if (lid) {
    void fetch(`/api/lease/${encodeURIComponent(lid)}/release`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
      },
      body: JSON.stringify({}),
    }).catch(() => {});
  }
}

export async function acquireFieldLease(targetId: string, field: string): Promise<void> {
  if (state.sinBackend) return;
  if (
    state.activeLease &&
    state.activeLease.targetId === targetId &&
    state.activeLease.field === field &&
    (state.activeLease.status === 'granted' || state.activeLease.status === 'pending')
  ) {
    return;
  }
  releaseActiveLeaseOnUnmount();
  leaseSeq += 1;
  const mySeq = leaseSeq;
  setState({
    activeLease: {
      targetId,
      field,
      leaseId: null,
      status: 'pending',
    },
  });

  try {
    const res = await fetch('/api/lease', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
      },
      body: JSON.stringify({ target: targetId, field }),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as {
      ok?: boolean;
      lease_id?: string;
      code?: string;
      msg?: string;
    } | null;

    if (res.status === 401 || (res.status === 403 && data?.code === 'csrf_failed')) {
      handleSessionExpired();
      return;
    }

    if (leaseSeq !== mySeq) {
      if (data?.lease_id) {
        void fetch(`/api/lease/${encodeURIComponent(data.lease_id)}/release`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
          },
          body: JSON.stringify({}),
        }).catch(() => {});
      }
      return;
    }

    if (res.ok && data?.ok && data.lease_id) {
      const lid = data.lease_id;
      setState({
        activeLease: {
          targetId,
          field,
          leaseId: lid,
          status: 'granted',
        },
      });
      clearLeaseTimer();
      leaseRenewTimer = window.setInterval(() => {
        const current = state.activeLease;
        if (!current || current.leaseId !== lid) {
          clearLeaseTimer();
          return;
        }
        void fetch(`/api/lease/${encodeURIComponent(lid)}/renew`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
          },
          body: JSON.stringify({}),
        })
          .then((r) => {
            markBackendAlive();
            if (r.status === 401) {
              handleSessionExpired();
              return;
            }
            // Una renovación rechazada (409 lease_expired u otra) deja al backend sin préstamo:
            // la web no puede seguir dando el campo por suyo (revisión de Sol, F05).
            if (!r.ok && state.activeLease?.leaseId === lid) {
              clearLeaseTimer();
              setState({
                activeLease: {
                  targetId,
                  field,
                  leaseId: null,
                  status: 'denied',
                  reason: 'El préstamo de este campo caducó: sal del campo y vuelve a entrar.',
                },
              });
            }
          })
          .catch(() => {
            markBackendDown();
          });
      }, 1000);
    } else {
      setState({
        activeLease: {
          targetId,
          field,
          leaseId: null,
          status: 'denied',
          reason: data?.msg ?? data?.code ?? 'No se pudo obtener el préstamo',
        },
      });
    }
  } catch {
    markBackendDown();
    if (leaseSeq === mySeq) {
      setState({
        activeLease: {
          targetId,
          field,
          leaseId: null,
          status: 'denied',
          reason: 'Sin conexión con el backend: no se puede editar',
        },
      });
    }
  }
}

export function releaseFieldLease(targetId: string, field: string): void {
  const cur = state.activeLease;
  if (!cur || cur.targetId !== targetId || cur.field !== field) return;
  leaseSeq += 1;
  releaseActiveLeaseOnUnmount();
}

// Scene Operations (POST /api/scene/ops)
export interface SceneOp {
  name: string;
  target?: string;
  args?: Record<string, unknown>;
}

// Los cambios del documento van en fila: cada tanda se construye cuando le toca y solo con un
// documento que ya incluya las tandas confirmadas antes (revisión de Sol, F01 y R2-01). Así un
// movimiento que manda X y Z toma la otra coordenada del documento bueno y no pisa la edición
// anterior.
let commitChain: Promise<unknown> = Promise.resolve();
// Última revisión que el backend devolvió a una tanda nuestra, por documento: la tanda siguiente no
// se construye hasta que el documento de la web la alcance.
let lastAck: { docId: string; rev: number } | null = null;
// Pide releer la escena antes de la tanda siguiente: hay una tanda cuyo efecto aún no se ha leído
// (R2-04).
let resyncNeeded = false;
// Generación de la sesión: sube con cada sesión nueva. Una tanda encolada en otra sesión no sale
// nunca, ni toca el estado al volver de una espera (revisión de Sol, SEG-01).
let sessionGen = 0;

type OpsContext = { targetId?: string; field?: string; rawValue?: string };

// Una tanda que se quedó sin respuesta en el plazo: el backend pudo aplicarla o no, y una lectura de
// la escena no lo demuestra (puede llegar antes que ella). Antes de la tanda siguiente se vuelve a
// mandar tal cual, con el mismo request_id: el backend no la aplica dos veces y su respuesta dice qué
// pasó (revisión de Sol, SEG-02).
interface UncertainOps {
  body: string;
  docId: string;
  context: OpsContext | undefined;
  genAtSend: number;
  sessionAt: number;
}
let uncertain: UncertainOps | null = null;

interface OpsResponse {
  ok?: boolean;
  rev?: number;
  code?: string;
  pointer?: string;
  msg?: string;
  created?: string[];
  errors?: Array<{ code: string; pointer: string; msg: string }>;
}

const REQUEST_TIMEOUT_MS = 10000;
const FRESH_ATTEMPTS = 3;
const FRESH_WAIT_MS = 300;

// Lo que devuelve un constructor cuando el valor ya es el del documento releído: no hay nada que
// mandar (R2-05).
export const NO_CHANGE = 'sin-cambios' as const;
export type SceneOpsBuilder = () => SceneOp[] | null | typeof NO_CHANGE;

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
}

// Ninguna petición de la escena se queda colgada para siempre: pasado el plazo se cancela (R2-04),
// también si lo que no termina de llegar es el cuerpo de la respuesta (revisión de Sol, SEG-03).
async function fetchJsonWithTimeout(
  input: string,
  init: RequestInit = {}
): Promise<{ res: Response; data: unknown }> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(input, { ...init, signal: ctl.signal });
    let data: unknown = null;
    try {
      data = await res.json();
    } catch (err) {
      if (isAbortError(err)) throw err;
      data = null;
    }
    return { res, data };
  } finally {
    window.clearTimeout(timer);
  }
}

function isDocFresh(): boolean {
  if (resyncNeeded || !state.docInfo) return false;
  if (!lastAck || lastAck.docId !== state.docInfo.doc_id) return true;
  return state.docInfo.rev >= lastAck.rev;
}

// Antes de construir una tanda, el documento de la web tiene que incluir las anteriores. Si la
// lectura autoritativa falla se reintenta un poco; si sigue sin llegar, la tanda no sale (R2-01).
// Una lectura que sí llega, hecha después de las tandas anteriores (y de resolver la que estuviera en
// duda), es la verdad del backend aunque su revisión no alcance la última confirmada (una escena
// reiniciada, o la respuesta simulada de una prueba): con ella se sigue.
async function ensureFreshDoc(): Promise<boolean> {
  let fresh = isDocFresh();
  for (let attempt = 0; attempt < FRESH_ATTEMPTS && !fresh; attempt++) {
    if (attempt > 0) await new Promise((r) => window.setTimeout(r, FRESH_WAIT_MS));
    if (await fetchAuthoritativeScene(false)) {
      resyncNeeded = false;
      lastAck = null;
      fresh = true;
    }
  }
  if (!fresh) return false;
  if (state.notice?.kind === 'escena-sin-releer' || state.notice?.kind === 'sin-respuesta') {
    setState({ notice: null });
  }
  return true;
}

// Con una sesión nueva, la fila empieza de cero: nada de la anterior la retiene ni sale ya.
export function resetCommitQueue(): void {
  sessionGen += 1;
  commitChain = Promise.resolve();
  lastAck = null;
  resyncNeeded = false;
  uncertain = null;
}

function opsPostInit(body: string): RequestInit {
  return {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
    },
    body,
  };
}

export function commitSceneOps(
  label: string,
  ops: SceneOp[] | SceneOpsBuilder,
  context?: OpsContext
): Promise<boolean> {
  // La generación del borrador, la sesión y el documento se toman al encolar (ver commitSceneOpsNow).
  const key = context?.targetId && context?.field ? `${context.targetId}:${context.field}` : null;
  const genAtEnqueue = key ? draftGen[key] ?? 0 : 0;
  const sessionAt = sessionGen;
  const docIdAtEnqueue = state.docInfo?.doc_id ?? null;
  const run = commitChain.then(() =>
    commitSceneOpsNow(label, ops, context, genAtEnqueue, sessionAt, docIdAtEnqueue)
  );
  commitChain = run.catch(() => undefined);
  return run;
}

// Solo una respuesta terminal dice qué pasó con una tanda: un 5xx o un cuerpo ilegible no lo dicen
// (pudo aplicarse o no), así que la tanda sigue en duda (revisión de Sol, SEG-02).
function isTerminalOpsResponse(res: Response, data: unknown): boolean {
  return res.status < 500 && data !== null && typeof data === 'object';
}

function markUncertain(
  body: string,
  docId: string,
  context: OpsContext | undefined,
  genAtSend: number,
  sessionAt: number
): void {
  uncertain = { body, docId, context, genAtSend, sessionAt };
  resyncNeeded = true;
  setState({
    notice: {
      kind: 'sin-respuesta',
      message:
        'El backend no respondió a tiempo: el cambio puede haberse aplicado o no. Se comprueba antes del siguiente.',
    },
  });
}

// Vuelve a mandar la tanda en duda, tal cual. Devuelve si ya se sabe qué pasó con ella.
async function resolveUncertain(): Promise<boolean> {
  const u = uncertain;
  if (!u) return true;
  try {
    const { res, data } = await fetchJsonWithTimeout('/api/scene/ops', opsPostInit(u.body));
    if (u.sessionAt !== sessionGen) return false;
    markBackendAlive();
    if (!isTerminalOpsResponse(res, data)) return false;
    uncertain = null;
    // Su efecto tiene que leerse antes de construir la tanda siguiente.
    resyncNeeded = true;
    await handleOpsResponse(res, data as OpsResponse | null, u.context, u.genAtSend, u.docId);
    return true;
  } catch (err) {
    if (u.sessionAt !== sessionGen) return false;
    if (!isAbortError(err)) markBackendDown();
    return false;
  }
}

async function commitSceneOpsNow(
  label: string,
  opsOrBuilder: SceneOp[] | SceneOpsBuilder,
  context: OpsContext | undefined,
  genAtEnqueue: number,
  sessionAt: number,
  docIdAtEnqueue: string | null
): Promise<boolean> {
  // Una tanda de otra sesión o de otro documento no sale, ni toca el estado al volver de una espera:
  // su intención era para lo que había entonces (revisión de Sol, SEG-01).
  const stale = () =>
    sessionAt !== sessionGen ||
    (docIdAtEnqueue !== null && state.docInfo !== null && state.docInfo.doc_id !== docIdAtEnqueue);
  if (stale()) return false;
  if (state.sinBackend || !state.docInfo) return false;
  const fieldKey =
    context?.targetId && context?.field ? `${context.targetId}:${context.field}` : null;
  // El borrador que esta tanda iba a confirmar ya no está: lo confirmó una tanda anterior (salir del
  // campo con la respuesta de Intro aún en camino, N2) o se descartó con Esc. Mandarlo ahora pisaría
  // lo que haya llegado después, como un cambio de la IA. Si en cambio hay un borrador más nuevo,
  // esta confirmación se pidió expresamente y sale igual, y su éxito no borra ese borrador (R2-02).
  if (fieldKey && (draftGen[fieldKey] ?? 0) !== genAtEnqueue && state.drafts[fieldKey] === undefined) {
    return true;
  }
  if (uncertain && !(await resolveUncertain())) {
    if (stale()) return false;
    setState({
      notice: {
        kind: 'sin-respuesta',
        message:
          'El backend sigue sin responder a un cambio anterior: este no se ha mandado y sigue en su campo.',
      },
    });
    return false;
  }
  if (stale()) return false;
  if (!(await ensureFreshDoc())) {
    if (stale()) return false;
    setState({
      notice: {
        kind: 'escena-sin-releer',
        message: 'No se pudo releer la escena: el cambio no se ha mandado y sigue en su campo.',
      },
    });
    return false;
  }
  if (stale()) return false;
  if (state.sinBackend || !state.docInfo) return false;
  // Tras las esperas (la tanda en duda y la lectura), el borrador pudo quedar confirmado o descartado:
  // se vuelve a comprobar antes de construir (revisión de Sol, pasada del seguimiento).
  if (fieldKey && (draftGen[fieldKey] ?? 0) !== genAtEnqueue && state.drafts[fieldKey] === undefined) {
    return true;
  }
  const built = typeof opsOrBuilder === 'function' ? opsOrBuilder() : opsOrBuilder;
  if (built === NO_CHANGE) {
    // El valor ya es el del documento releído: no se manda nada (R2-05).
    if (context?.targetId && context?.field && fieldKey && (draftGen[fieldKey] ?? 0) === genAtEnqueue) {
      clearFieldErrorAndDraft(context.targetId, context.field);
    }
    return true;
  }
  const ops = built;
  if (!ops || ops.length === 0) return false;
  const reqId = nextRequestId('ops');
  const genAtSend = genAtEnqueue;
  const docIdAtSend = state.docInfo.doc_id;
  const body = JSON.stringify({
    doc_id: docIdAtSend,
    request_id: reqId,
    base_rev: state.docInfo.rev,
    label,
    ops,
  });
  try {
    const { res, data } = await fetchJsonWithTimeout('/api/scene/ops', opsPostInit(body));
    if (stale()) return false;
    markBackendAlive();
    // Un 5xx o un cuerpo ilegible no dicen si se aplicó: en duda, como sin respuesta (SEG-02).
    if (!isTerminalOpsResponse(res, data)) {
      markUncertain(body, docIdAtSend, context, genAtSend, sessionAt);
      return false;
    }
    return await handleOpsResponse(res, data as OpsResponse | null, context, genAtSend, docIdAtSend);
  } catch (err) {
    if (stale()) return false;
    // Sin respuesta en el plazo: el backend pudo aplicarla o no. El borrador se queda en su campo y,
    // antes de la tanda siguiente, se vuelve a mandar esta tal cual para saberlo (SEG-02).
    if (isAbortError(err)) {
      markUncertain(body, docIdAtSend, context, genAtSend, sessionAt);
      return false;
    }
    markBackendDown();
    return false;
  }
}

async function handleOpsResponse(
  res: Response,
  data: OpsResponse | null,
  context: OpsContext | undefined,
  genAtSend: number,
  docIdAtSend: string
): Promise<boolean> {
  const fieldKey =
    context?.targetId && context?.field ? `${context.targetId}:${context.field}` : null;

  if (res.status === 401 || (res.status === 403 && data?.code === 'csrf_failed')) {
    handleSessionExpired();
    return false;
  }

  if (res.ok && data?.ok) {
    if (typeof data.rev === 'number') {
      if (!lastAck || lastAck.docId !== docIdAtSend || data.rev > lastAck.rev) {
        lastAck = { docId: docIdAtSend, rev: data.rev };
      }
    }
    if (Array.isArray(data.created) && data.created.length > 0) {
      pendingCreatedEntityId = data.created[0];
    }
    // Un borrador posterior al envío (otra tecla, otro valor) no se borra con este éxito.
    if (context?.targetId && context?.field && fieldKey && (draftGen[fieldKey] ?? 0) === genAtSend) {
      clearFieldErrorAndDraft(context.targetId, context.field);
    }
    await fetchAuthoritativeScene(true);
    return true;
  }

  const firstErr =
    Array.isArray(data?.errors) && data.errors.length > 0
      ? data.errors[0]
      : {
          code: data?.code ?? String(res.status),
          pointer: data?.pointer ?? '',
          msg: data?.msg ?? 'Error de validación',
        };

  if (context?.targetId && context?.field) {
    const key = `${context.targetId}:${context.field}`;
    // El borrador cambió o se descartó (Esc) mientras volvía la respuesta: no se resucita.
    if ((draftGen[key] ?? 0) !== genAtSend) return false;
    // Su entidad ya no existe (la borró otra edición): tampoco (revisión de Sol, R2-03).
    if (
      context.targetId !== 'ambiente' &&
      !state.doc?.entities.some((e) => e.id === context.targetId)
    ) {
      return false;
    }
    const rawValue = context.rawValue ?? state.drafts[key] ?? '';
    const rej: RejectedDraft = {
      targetId: context.targetId,
      field: context.field,
      rawValue,
      code: firstErr.code,
      msg: firstErr.msg,
      pointer: firstErr.pointer,
    };
    const valItem: ValidationErrorItem = {
      id: key,
      pointer: firstErr.pointer,
      code: firstErr.code,
      msg: firstErr.msg,
      targetId: context.targetId,
      field: context.field,
    };
    setState((prev) => ({
      drafts: { ...prev.drafts, [key]: rawValue },
      rejectedDrafts: { ...prev.rejectedDrafts, [key]: rej },
      validationErrors: [
        ...prev.validationErrors.filter((e) => e.id !== key),
        valItem,
      ],
    }));
  } else {
    const errId = `op-err-${Date.now()}`;
    setState((prev) => ({
      validationErrors: [
        ...prev.validationErrors,
        {
          id: errId,
          pointer: firstErr.pointer,
          code: firstErr.code,
          msg: firstErr.msg,
          targetId: null,
          field: null,
        },
      ],
    }));
  }
  return false;
}

// Generación de cada borrador: sube cada vez que el borrador cambia o se descarta. La respuesta de
// un envío viejo (un 422 que llega después de Esc) no puede resucitarlo (revisión de Sol, F06).
const draftGen: Record<string, number> = {};
function bumpDraftGen(key: string): void {
  draftGen[key] = (draftGen[key] ?? 0) + 1;
}

export function clearFieldErrorAndDraft(targetId: string, field: string) {
  const key = `${targetId}:${field}`;
  bumpDraftGen(key);
  setState((prev) => {
    const nextDrafts = { ...prev.drafts };
    const nextRej = { ...prev.rejectedDrafts };
    delete nextDrafts[key];
    delete nextRej[key];
    return {
      drafts: nextDrafts,
      rejectedDrafts: nextRej,
      validationErrors: prev.validationErrors.filter((e) => e.id !== key),
    };
  });
}

export function setFieldDraft(targetId: string, field: string, value: string) {
  const key = `${targetId}:${field}`;
  bumpDraftGen(key);
  setState((prev) => ({
    drafts: { ...prev.drafts, [key]: value },
  }));
}

export const FIELD_SPANISH_NAMES: Record<string, string> = {
  cls: 'clase',
  name: 'nombre',
  x: 'X',
  z: 'Z',
  yaw: 'rumbo',
  fecha: 'fecha',
  hora: 'hora',
  nubes: 'nubes',
  niebla: 'niebla',
  lluvia: 'lluvia',
  viento: 'viento',
};

export async function triggerUndoRedo(redo: boolean): Promise<void> {
  if (state.sinBackend) {
    setState({
      notice: {
        kind: 'sin-backend',
        message: 'Sin conexión con el backend: no se puede deshacer ni rehacer.',
      },
    });
    return;
  }
  if (!state.docInfo) return;
  const endpoint = redo ? '/api/scene/redo' : '/api/scene/undo';
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
      },
      body: JSON.stringify({
        doc_id: state.docInfo.doc_id,
        request_id: nextRequestId(redo ? 'redo' : 'undo'),
      }),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as {
      ok?: boolean;
      code?: string;
      partial?: Array<{ target: string; field: string; why: string }>;
    } | null;

    if (res.status === 401 || (res.status === 403 && data?.code === 'csrf_failed')) {
      handleSessionExpired();
      return;
    }

    if (res.status === 409 && (data?.code === 'nothing_to_undo' || data?.code === 'nothing_to_redo')) {
      setFlash(redo ? 'Nada que rehacer' : 'Nada que deshacer');
      return;
    }

    if (res.ok && data?.ok) {
      await fetchAuthoritativeScene(true);
      if (Array.isArray(data.partial) && data.partial.length > 0) {
        const parts = data.partial.map((p) => {
          const ent = state.doc?.entities.find((e) => e.id === p.target);
          const entName =
            p.target === 'ambiente' ? 'Ambiente' : ent ? ent.name : p.target;
          const fName = FIELD_SPANISH_NAMES[p.field] ?? p.field;
          return `No se ${redo ? 'rehizo' : 'deshizo'} el ${fName} de «${entName}»: lo cambió después otra edición`;
        });
        setState({
          notice: {
            kind: 'deshacer-parcial',
            message: parts.join(' · '),
          },
        });
      }
    }
  } catch {
    markBackendDown();
  }
}

export async function triggerApplyScene(): Promise<void> {
  if (
    !state.docInfo ||
    state.applying ||
    state.sinBackend ||
    Object.keys(state.rejectedDrafts).length > 0
  ) {
    return;
  }
  setState({ applying: true, applyError: null });
  try {
    const res = await fetch('/api/apply', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
      },
      body: JSON.stringify({
        doc_id: state.docInfo.doc_id,
        rev: state.docInfo.rev,
        hash: state.docInfo.hash,
      }),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as {
      ok?: boolean;
      code?: string;
      pointer?: string;
      msg?: string;
    } | null;
    if (res.status === 401 || (res.status === 403 && data?.code === 'csrf_failed')) {
      handleSessionExpired();
      return;
    }
    if (!res.ok) {
      setState({
        applyError: {
          code: data?.code ?? String(res.status),
          pointer: data?.pointer ?? '',
          msg: data?.msg ?? '',
        },
      });
    }
  } catch {
    markBackendDown();
    setState({ applyError: { code: 'network', pointer: '', msg: 'Error de red' } });
  } finally {
    setState({ applying: false });
  }
}

export async function triggerResetScene(): Promise<void> {
  if (!state.docInfo || state.sinBackend || state.applying || state.removing) return;
  setState({ removing: true, applyError: null });
  try {
    const res = await fetch('/api/reset', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
      },
      body: JSON.stringify({ doc_id: state.docInfo.doc_id }),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as {
      ok?: boolean;
      code?: string;
      pointer?: string;
      msg?: string;
    } | null;
    if (res.status === 401 || (res.status === 403 && data?.code === 'csrf_failed')) {
      handleSessionExpired();
      return;
    }
    if (res.status === 404) {
      setState({
        notice: {
          kind: 'quitar-no-disponible',
          message: 'Quitar del juego llega con F2',
        },
      });
      return;
    }
    if (!res.ok) {
      setState({
        applyError: {
          code: data?.code ?? String(res.status),
          pointer: data?.pointer ?? '',
          msg: data?.msg ?? '',
        },
      });
    }
  } catch {
    markBackendDown();
    setState({ applyError: { code: 'network', pointer: '', msg: 'Error de red' } });
  } finally {
    setState({ removing: false });
  }
}

export async function placeSelectedCatalogItem(): Promise<void> {
  const item = state.placingItem;
  if (!item || state.sinBackend || !state.doc) return;
  const { kind, cls } = item;
  const count = state.doc.entities.filter((e) => e.kind === kind).length;
  const cap = state.catalog?.caps?.[kind];
  if (typeof cap === 'number' && count >= cap) {
    setState({ placingItem: null });
    setFlash(`Tope de ${kind} alcanzado (${count} / ${cap})`);
    return;
  }
  setState({ placingItem: null });
  await commitSceneOps(`Colocar ${cls}`, [
    {
      name: 'entity.add',
      args: {
        kind,
        cls,
        name: cls,
        x: 7680,
        z: 7680,
        yaw: 0,
      },
    },
  ]);
}

export async function deleteSelectedEntities(): Promise<void> {
  if (state.sinBackend || !state.doc) return;
  const entityIds = state.selectedIds.filter((id) =>
    state.doc!.entities.some((e) => e.id === id)
  );
  if (entityIds.length === 0) return;
  const entities = entityIds
    .map((id) => state.doc!.entities.find((e) => e.id === id))
    .filter((e): e is SceneEntity => Boolean(e));

  const label =
    entities.length === 1
      ? `Borrar ${entities[0].name}`
      : `Borrar ${entities.length} entidades`;
  const ops: SceneOp[] = entities.map((e) => ({
    name: 'entity.delete',
    target: e.id,
    args: {},
  }));

  setState({ selectedIds: [] });
  await commitSceneOps(label, ops);
}

export function selectAllEntities(): void {
  const doc = state.doc;
  if (!doc) return;
  setState({ selectedIds: doc.entities.map((e) => e.id) });
}

export function openPropertiesAndFocus(): void {
  const api = dockApiRef;
  if (api) {
    openOrFocusPanel(api, state.mode, 'propiedades');
  }
  window.setTimeout(() => {
    const el = document.querySelector<HTMLElement>(
      '[data-panel="propiedades"] input:not([disabled]), [data-panel="propiedades"] select:not([disabled])'
    );
    el?.focus();
  }, 40);
}

export async function duplicateSelectedEntity(): Promise<void> {
  if (state.sinBackend || !state.doc) return;
  if (state.selectedIds.length !== 1) return;
  const ent = state.doc.entities.find((e) => e.id === state.selectedIds[0]);
  if (!ent || ent.kind === 'actor') return;
  const count = state.doc.entities.filter((e) => e.kind === ent.kind).length;
  const cap = state.catalog?.caps?.[ent.kind];
  if (typeof cap === 'number' && count >= cap) {
    setFlash(`Tope de ${ent.kind} alcanzado (${count} / ${cap})`);
    return;
  }
  const newX = Math.min(15360, +(ent.x + 2).toFixed(1));
  await commitSceneOps(`Duplicar ${ent.name}`, [
    {
      name: 'entity.add',
      args: {
        kind: ent.kind,
        cls: ent.cls,
        name: `${ent.name} (copia)`,
        x: newX,
        z: ent.z,
        yaw: ent.yaw,
      },
    },
  ]);
}

export function copySelectedCoordinates(): void {
  if (!state.doc || state.selectedIds.length !== 1) return;
  const ent = state.doc.entities.find((e) => e.id === state.selectedIds[0]);
  if (!ent) return;
  const text = `${ent.x}; ${ent.z}`;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    void navigator.clipboard.writeText(text).catch(() => {});
  }
  setFlash(`Coordenadas copiadas: ${text}`);
}

export function switchStudioMode(nextMode: ModeName): void {
  if (state.mode === nextMode) return;
  const api = dockApiRef;
  let currentLayout = state.layouts[state.mode];
  if (api) {
    try {
      currentLayout = api.toJSON() as unknown as Record<string, unknown>;
    } catch {
      // keep existing
    }
  }
  const nextLayouts = {
    ...state.layouts,
    [state.mode]: currentLayout,
  };
  setState({
    mode: nextMode,
    layouts: nextLayouts,
    placingItem: null,
  });
  if (api) {
    applyLayoutToDockview(api, nextMode, nextLayouts[nextMode]);
    try {
      const afterSwitch = api.toJSON() as unknown as Record<string, unknown>;
      setState((prev) => ({
        layouts: {
          ...prev.layouts,
          [nextMode]: afterSwitch,
        },
      }));
    } catch {
      // ignore
    }
  }
  scheduleProfileSave(false);
}

export function resetCurrentModeLayoutToFactory(): void {
  const api = dockApiRef;
  if (!api) return;
  suppressLayoutSave = true;
  try {
    applyFactoryLayoutForMode(api, state.mode);
    const serialized = api.toJSON() as unknown as Record<string, unknown>;
    setState((prev) => ({
      layouts: {
        ...prev.layouts,
        [prev.mode]: serialized,
      },
    }));
  } finally {
    window.setTimeout(() => {
      suppressLayoutSave = false;
    }, 50);
  }
  scheduleProfileSave(false);
}

export function applyCurrentModePropsLeftPreset(): void {
  const api = dockApiRef;
  if (!api) return;
  suppressLayoutSave = true;
  try {
    applyPropsLeftLayoutForMode(api, state.mode);
    const serialized = api.toJSON() as unknown as Record<string, unknown>;
    setState((prev) => ({
      layouts: {
        ...prev.layouts,
        [prev.mode]: serialized,
      },
    }));
  } finally {
    window.setTimeout(() => {
      suppressLayoutSave = false;
    }, 50);
  }
  scheduleProfileSave(false);
}

export function updateShortcutBinding(
  actionId: string,
  combo: string,
  replacedActionId?: string
): void {
  setState((prev) => {
    const next = { ...prev.keymap, [actionId]: combo };
    if (replacedActionId) {
      next[replacedActionId] = null;
    }
    return { keymap: next };
  });
  scheduleProfileSave(false);
}

export function resetAllShortcutsToDefault(): void {
  setState({ keymap: getDefaultKeymap() });
  scheduleProfileSave(false);
}
