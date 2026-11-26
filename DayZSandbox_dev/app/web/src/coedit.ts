// F6-web parte 2: la coedición en la web (brief §2-§4). La web pinta lo que dice el backend:
// la vista de /api/coedit, las tandas de /api/scene/changes y de scene.commit, y la propuesta
// del evento apply.request. Nunca la respuesta de un POST.
import { useSyncExternalStore } from 'react';
import {
  FIELD_SPANISH_NAMES,
  getState,
  handleSessionExpired,
  markBackendAlive,
  markBackendDown,
  nextRequestId,
} from './store';

export interface BatchRecord {
  batch: string;
  rev: number;
  author: { role: string; id?: string };
  label: string | null;
  ops: Array<{ name?: string; target?: string }>;
  created: string[];
  partial: Array<{ target: string; field: string; why?: string }>;
  fp: Array<[string, string]>;
  at_ms: number;
}

export interface CoeditView {
  paused: boolean;
  aiAgeMs: number | null;
  readAtPerf: number;
  canUndo: boolean;
  canRedo: boolean;
  historySince: number;
}

export interface CoeditState {
  view: CoeditView | null;
  batches: BatchRecord[]; // ordenadas por rev, de menor a mayor
  historyGap: boolean;
  proposal: { rev: number; hash: string; at_ms: number } | null;
  proposalError: { code: string; msg: string } | null;
  approving: boolean;
  pausing: boolean;
  reverting: string | null;
  aiTouched: Record<string, number>; // id -> performance.now() del evento
  lastAiCommitPerf: number | null;
  notice: { kind: 'deshacer-tanda-parcial' | 'tanda-no-deshecha'; message: string } | null;
}

export const AI_FRESH_MS = 10000;
export const AI_EDITING_MS = 3000;
export const AI_ACTIVE_MS = 35000;

function initial(): CoeditState {
  return {
    view: null,
    batches: [],
    historyGap: false,
    proposal: null,
    proposalError: null,
    approving: false,
    pausing: false,
    reverting: null,
    aiTouched: {},
    lastAiCommitPerf: null,
    notice: null,
  };
}

let cs: CoeditState = initial();
const listeners = new Set<() => void>();
// Historial completo hasta esta rev. Un scene.commit suelto no lo mueve salvo que sea la siguiente
// (Sol R21 W2-01): si no, queda un tramo sin pedir.
let coveredRev = -1;

function set(patch: Partial<CoeditState> | ((prev: CoeditState) => Partial<CoeditState>)) {
  const p = typeof patch === 'function' ? patch(cs) : patch;
  cs = { ...cs, ...p };
  for (const l of listeners) l();
}

export function getCoedit(): CoeditState {
  return cs;
}

export function useCoedit(): CoeditState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    getCoedit
  );
}

// Cada lectura de /api/coedit lleva su número; una respuesta más vieja que la ya pintada no cuenta
// (Sol R21 W2-04). Al reiniciar, las que estén en vuelo quedan viejas.
let coeditSeq = 0;
let coeditApplied = 0;

export function resetCoedit(): void {
  coveredRev = -1;
  coeditApplied = coeditSeq;
  cs = initial();
  for (const l of listeners) l();
}

function csrfHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-CSRF-Token': localStorage.getItem('csrf') ?? '',
  };
}

function isAuthFailure(status: number, data: { code?: string } | null): boolean {
  return status === 401 || (status === 403 && data?.code === 'csrf_failed');
}

// --- lecturas -------------------------------------------------------------

export async function refreshCoedit(): Promise<void> {
  const seq = ++coeditSeq;
  try {
    const res = await fetch('/api/coedit', { credentials: 'same-origin' });
    if (res.status === 401) {
      handleSessionExpired();
      return;
    }
    markBackendAlive();
    if (!res.ok) return;
    const d = (await res.json().catch(() => null)) as {
      paused?: boolean;
      ai_last_call_age_ms?: number | null;
      can_undo?: boolean;
      can_redo?: boolean;
      history_since?: number;
    } | null;
    if (!d || seq <= coeditApplied) return;
    coeditApplied = seq;
    set({
      view: {
        paused: d.paused === true,
        aiAgeMs: typeof d.ai_last_call_age_ms === 'number' ? d.ai_last_call_age_ms : null,
        readAtPerf: performance.now(),
        canUndo: d.can_undo === true,
        canRedo: d.can_redo === true,
        historySince: typeof d.history_since === 'number' ? d.history_since : 0,
      },
    });
  } catch {
    markBackendDown();
  }
}

function mergeBatches(recs: BatchRecord[]): void {
  if (recs.length === 0) return;
  set((prev) => {
    const byId = new Map(prev.batches.map((b) => [b.batch, b]));
    for (const r of recs) {
      if (r && typeof r.batch === 'string' && typeof r.rev === 'number') byId.set(r.batch, r);
    }
    const batches = [...byId.values()].sort((a, b) => a.rev - b.rev);
    return { batches };
  });
}

let historyInFlight = false;
let historyAgain = false;
let wantRev = -1;

// Una sola lectura a la vez; lo que se pida mientras tanto se lee al acabar.
export async function loadHistory(minRev = -1): Promise<void> {
  if (minRev > wantRev) wantRev = minRev;
  if (historyInFlight) {
    historyAgain = true;
    return;
  }
  historyInFlight = true;
  try {
    do {
      historyAgain = false;
      await loadHistoryOnce();
    } while (historyAgain);
  } finally {
    historyInFlight = false;
  }
}

async function loadHistoryOnce(): Promise<void> {
  try {
    // La primera vez hace falta saber desde dónde guarda tandas el backend (history_since).
    if (coveredRev < 0) await refreshCoedit();
    const info = getState().docInfo;
    if (!info) return;
    if (coveredRev >= 0 && coveredRev >= Math.max(info.rev, wantRev)) return;
    const knownRev = coveredRev;
    const floor = cs.view ? cs.view.historySince : 0;
    // La rev 1 es el documento de partida, sin tanda: solo falta algo si el suelo es mayor.
    if (knownRev < 0 && floor > 1) set({ historyGap: true });
    // Desde el suelo: todas las tandas que el backend guarda, sin ventana (Sol R21 W2-03).
    const since = knownRev >= 0 ? knownRev : Math.max(floor, 0);
    const res = await fetch(`/api/scene/changes?since_rev=${since}&timeout_s=0`, {
      credentials: 'same-origin',
    });
    if (res.status === 401) {
      handleSessionExpired();
      return;
    }
    markBackendAlive();
    const d = (await res.json().catch(() => null)) as {
      ok?: boolean;
      code?: string;
      rev?: number;
      batches?: BatchRecord[];
    } | null;
    if (!d) return;
    if (d.ok && Array.isArray(d.batches)) {
      mergeBatches(d.batches);
      if (typeof d.rev === 'number' && d.rev > coveredRev) coveredRev = d.rev;
    } else if (d.code === 'stale_base') {
      // Lo de antes ya no está (nota de §4.4), pero lo que el backend aún guarda se pide desde su
      // suelo (Sol R21 W2-02). Si ya se pidió desde el suelo, se sigue desde la revisión actual.
      set({ historyGap: true });
      if (knownRev >= 0) {
        coveredRev = -1;
        historyAgain = true;
      } else if (info.rev > coveredRev) {
        coveredRev = info.rev;
      }
    }
  } catch {
    markBackendDown();
  }
}

// --- eventos del SSE --------------------------------------------------------

export function onCommitEvent(rec: BatchRecord): void {
  if (!rec || typeof rec.batch !== 'string') return;
  mergeBatches([rec]);
  if (typeof rec.rev === 'number') {
    if (coveredRev >= 0 && rec.rev === coveredRev + 1) coveredRev = rec.rev;
    else if (rec.rev > coveredRev) void loadHistory(rec.rev);
  }
  if (rec.author?.role === 'ai') {
    const now = performance.now();
    const touched: Record<string, number> = {};
    for (const pair of rec.fp || []) {
      if (Array.isArray(pair) && typeof pair[0] === 'string') touched[pair[0]] = now;
    }
    for (const id of rec.created || []) touched[id] = now;
    set((prev) => ({ aiTouched: { ...prev.aiTouched, ...touched }, lastAiCommitPerf: now }));
  }
  void refreshCoedit();
}

export function onAiStateEvent(): void {
  void refreshCoedit();
}

export function onApplyRequestEvent(data: {
  rev?: number;
  hash?: string;
  author?: { role?: string };
  at_ms?: number;
}): void {
  if (data?.author?.role !== 'ai') return;
  if (typeof data.rev !== 'number' || typeof data.hash !== 'string') return;
  set({
    proposal: { rev: data.rev, hash: data.hash, at_ms: typeof data.at_ms === 'number' ? data.at_ms : 0 },
    proposalError: null,
  });
}

// --- derivados ---------------------------------------------------------------

// Una tanda está deshecha si la última inversa que la nombra es un undo o un revert (§3).
export function undoneBatches(batches: BatchRecord[]): Set<string> {
  const last = new Map<string, string>();
  for (const b of batches) {
    const op = b.ops && b.ops[0];
    if (op && (op.name === 'undo' || op.name === 'redo' || op.name === 'revert') && typeof op.target === 'string') {
      last.set(op.target, op.name);
    }
  }
  const out = new Set<string>();
  for (const [target, name] of last) if (name !== 'redo') out.add(target);
  return out;
}

export function isInverse(b: BatchRecord): boolean {
  const name = b.ops && b.ops[0] && b.ops[0].name;
  return name === 'undo' || name === 'redo' || name === 'revert';
}

// «N cambios» = las operaciones de la tanda, como en el prototipo (estudio.html:3160).
export function changeCount(b: BatchRecord): number {
  return Array.isArray(b.ops) ? b.ops.length : 0;
}

export function batchLabel(b: BatchRecord): string {
  return typeof b.label === 'string' && b.label !== '' ? b.label : 'Sin nombre';
}

export function aiAgeNow(view: CoeditView | null, now: number): number | null {
  if (!view || view.aiAgeMs === null) return null;
  return view.aiAgeMs + Math.max(0, now - view.readAtPerf);
}

export function aiLightText(sinBackend: boolean, c: CoeditState, now: number): string {
  if (sinBackend || !c.view) return 'IA · sin datos';
  if (c.view.paused) return 'IA en pausa';
  if (c.lastAiCommitPerf !== null && now - c.lastAiCommitPerf < AI_EDITING_MS) return 'IA editando';
  const age = aiAgeNow(c.view, now);
  if (age === null) return 'MCP apagado';
  return age < AI_ACTIVE_MS ? 'IA conectada' : 'IA inactiva';
}

export function formatAgo(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec <= 59) return `hace ${sec} s`;
  const min = Math.floor(sec / 60);
  if (min <= 59) return `hace ${min} min`;
  return `hace ${Math.floor(min / 60)} h`;
}

// --- acciones -----------------------------------------------------------------

export async function setAiPaused(paused: boolean): Promise<void> {
  if (cs.pausing || getState().sinBackend) return;
  set({ pausing: true });
  try {
    const res = await fetch('/api/ai/pause', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(),
      body: JSON.stringify({ paused }),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as { code?: string } | null;
    if (isAuthFailure(res.status, data)) {
      handleSessionExpired();
      return;
    }
    // Sin optimismo (§4.2): el estado lo dice /api/coedit, no esta respuesta.
    await refreshCoedit();
  } catch {
    markBackendDown();
  } finally {
    set({ pausing: false });
  }
}

function entityName(id: string): string {
  if (id === 'ambiente') return 'Ambiente';
  const ent = getState().doc?.entities.find((e) => e.id === id);
  return ent ? ent.name : id;
}

export async function revertBatch(batch: string): Promise<void> {
  const info = getState().docInfo;
  if (!info || cs.reverting || getState().sinBackend) return;
  set({ reverting: batch, notice: null });
  try {
    const res = await fetch(`/api/scene/batches/${encodeURIComponent(batch)}/revert`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(),
      body: JSON.stringify({ doc_id: info.doc_id, request_id: nextRequestId('revert') }),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as {
      ok?: boolean;
      code?: string;
      msg?: string;
      partial?: Array<{ target: string; field: string }>;
    } | null;
    if (isAuthFailure(res.status, data)) {
      handleSessionExpired();
      return;
    }
    if (res.ok && data?.ok) {
      if (Array.isArray(data.partial) && data.partial.length > 0) {
        const parts = data.partial.map(
          (p) => `Se conserva tu cambio en el ${FIELD_SPANISH_NAMES[p.field] ?? p.field} de «${entityName(p.target)}»`
        );
        set({ notice: { kind: 'deshacer-tanda-parcial', message: parts.join(' · ') } });
      }
    } else {
      set({
        notice: {
          kind: 'tanda-no-deshecha',
          message: `No se deshizo la tanda (${data?.code ?? res.status})${data?.msg ? ': ' + data.msg : ''}`,
        },
      });
    }
  } catch {
    markBackendDown();
  } finally {
    set({ reverting: null });
  }
}

export async function approveProposal(): Promise<void> {
  const p = cs.proposal;
  const info = getState().docInfo;
  if (!p || !info || cs.approving || getState().sinBackend) return;
  if (info.rev !== p.rev) return;
  set({ approving: true, proposalError: null });
  try {
    const res = await fetch('/api/apply', {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(),
      // La revisión y el hash de la propuesta, no los pintados (coedición §2.7).
      body: JSON.stringify({ doc_id: info.doc_id, rev: p.rev, hash: p.hash }),
    });
    markBackendAlive();
    const data = (await res.json().catch(() => null)) as { code?: string; msg?: string } | null;
    if (isAuthFailure(res.status, data)) {
      handleSessionExpired();
      return;
    }
    // Si mientras tanto llegó otra propuesta, esta respuesta no la toca (Sol R21 W2-06).
    if (cs.proposal !== p) return;
    if (res.ok) {
      set({ proposal: null });
    } else {
      set({ proposalError: { code: data?.code ?? String(res.status), msg: data?.msg ?? '' } });
    }
  } catch {
    markBackendDown();
  } finally {
    set({ approving: false });
  }
}

export function dismissProposal(): void {
  set({ proposal: null, proposalError: null });
}

export function dismissCoeditNotice(): void {
  set({ notice: null });
}

// Quita las marcas «IA · hace» caducadas; lo llama el reloj de un segundo de App.
export function pruneAiTouched(now: number): void {
  const keys = Object.keys(cs.aiTouched);
  if (keys.every((k) => now - cs.aiTouched[k] < AI_FRESH_MS)) return;
  const next: Record<string, number> = {};
  for (const k of keys) if (now - cs.aiTouched[k] < AI_FRESH_MS) next[k] = cs.aiTouched[k];
  set({ aiTouched: next });
}
