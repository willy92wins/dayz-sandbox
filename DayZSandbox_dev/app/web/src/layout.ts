import { DockviewApi, SerializedDockview } from 'dockview-react';
import { EscenaPanelId, ModeName, RodajePanelId, StudioPanelId } from './types';

export const ESCENA_PANELS: readonly EscenaPanelId[] = [
  'jerarquia',
  'mapa',
  'propiedades',
  'anadir',
  'actividad',
  'validacion',
  'historial',
  'ia',
];

export const RODAJE_PANELS: readonly RodajePanelId[] = [
  'camaras',
  'tomas',
  'mapa',
  'preparacion',
  'propiedades',
  'actividad',
  'vista-previa',
];

export const PANEL_TITLES: Record<StudioPanelId, string> = {
  jerarquia: 'Jerarquía',
  mapa: 'Mapa',
  propiedades: 'Propiedades',
  anadir: 'Añadir',
  actividad: 'Actividad',
  validacion: 'Validación',
  historial: 'Historial',
  ia: 'IA',
  camaras: 'Cámaras',
  tomas: 'Tomas',
  preparacion: 'Preparación',
  'vista-previa': 'Vista previa del mapa',
};

export function getAllowedPanelsForMode(mode: ModeName): readonly StudioPanelId[] {
  return mode === 'escena' ? ESCENA_PANELS : RODAJE_PANELS;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function validateAndSanitizeLayout(
  raw: unknown,
  mode: ModeName
): SerializedDockview | null {
  if (!isPlainObject(raw)) return null;

  const grid = raw.grid;
  const panels = raw.panels;
  if (!isPlainObject(grid) || !isPlainObject(panels)) return null;

  if (raw.floatingGroups !== undefined) {
    if (!Array.isArray(raw.floatingGroups) || raw.floatingGroups.length > 0) {
      return null;
    }
  }
  if (raw.popoutGroups !== undefined) {
    if (!Array.isArray(raw.popoutGroups) || raw.popoutGroups.length > 0) {
      return null;
    }
  }

  if (
    typeof grid.width !== 'number' ||
    !Number.isFinite(grid.width) ||
    grid.width <= 0 ||
    typeof grid.height !== 'number' ||
    !Number.isFinite(grid.height) ||
    grid.height <= 0 ||
    (grid.orientation !== 'HORIZONTAL' && grid.orientation !== 'VERTICAL')
  ) {
    return null;
  }

  const root = grid.root;
  if (
    !isPlainObject(root) ||
    root.type !== 'branch' ||
    !Array.isArray(root.data) ||
    root.data.length === 0
  ) {
    return null;
  }

  const allowedSet = new Set<string>(getAllowedPanelsForMode(mode));
  const panelKeys = Object.keys(panels);
  if (panelKeys.length === 0) return null;

  const sanitizedPanels: Record<string, Record<string, unknown>> = {};
  for (const key of panelKeys) {
    if (!allowedSet.has(key)) return null;
    const p = panels[key];
    if (!isPlainObject(p)) return null;
    if (p.id !== key) return null;
    const expectedTitle = PANEL_TITLES[key as StudioPanelId];
    sanitizedPanels[key] = {
      ...p,
      id: key,
      contentComponent: key,
      tabComponent: 'studioTab',
      title: expectedTitle,
    };
  }

  const seenViews = new Set<string>();
  const seenGroups = new Set<string>();

  function checkNode(node: unknown): boolean {
    if (!isPlainObject(node)) return false;
    if (
      node.size !== undefined &&
      (typeof node.size !== 'number' || !Number.isFinite(node.size) || node.size <= 0)
    ) {
      return false;
    }
    if (node.type === 'branch') {
      if (!Array.isArray(node.data) || node.data.length === 0) return false;
      for (const child of node.data) {
        if (!checkNode(child)) return false;
      }
      return true;
    }
    if (node.type === 'leaf') {
      const data = node.data;
      if (!isPlainObject(data)) return false;
      if (typeof data.id !== 'string' || data.id.length === 0 || seenGroups.has(data.id)) {
        return false;
      }
      seenGroups.add(data.id);
      if (!Array.isArray(data.views) || data.views.length === 0) return false;
      for (const v of data.views) {
        if (
          typeof v !== 'string' ||
          !allowedSet.has(v) ||
          !(v in sanitizedPanels) ||
          seenViews.has(v)
        ) {
          return false;
        }
        seenViews.add(v);
      }
      if (
        data.activeView !== undefined &&
        (typeof data.activeView !== 'string' || !data.views.includes(data.activeView))
      ) {
        return false;
      }
      return true;
    }
    return false;
  }

  if (!checkNode(root)) return null;
  if (seenViews.size !== panelKeys.length) return null;

  const clone = JSON.parse(JSON.stringify(raw)) as Record<string, unknown>;
  clone.panels = sanitizedPanels;
  clone.floatingGroups = [];
  clone.popoutGroups = [];
  return clone as unknown as SerializedDockview;
}

function addStudioPanel(
  api: DockviewApi,
  id: StudioPanelId,
  options?: {
    referencePanel?: StudioPanelId;
    direction?: 'left' | 'right' | 'above' | 'below' | 'within';
    initialWidth?: number;
    initialHeight?: number;
  }
) {
  return api.addPanel({
    id,
    component: id,
    tabComponent: 'studioTab',
    title: PANEL_TITLES[id],
    position: options?.referencePanel
      ? {
          referencePanel: options.referencePanel,
          direction: options.direction ?? 'within',
        }
      : undefined,
    initialWidth: options?.initialWidth,
    initialHeight: options?.initialHeight,
  });
}

export function applyEscenaFactoryLayout(api: DockviewApi): void {
  api.clear();
  const pJer = addStudioPanel(api, 'jerarquia', { initialWidth: 256 });
  addStudioPanel(api, 'mapa', { referencePanel: 'jerarquia', direction: 'right' });
  const pProp = addStudioPanel(api, 'propiedades', {
    referencePanel: 'mapa',
    direction: 'right',
    initialWidth: 320,
  });
  addStudioPanel(api, 'anadir', {
    referencePanel: 'propiedades',
    direction: 'within',
  });
  const pAct = addStudioPanel(api, 'actividad', {
    referencePanel: 'mapa',
    direction: 'below',
    initialHeight: 220,
  });
  addStudioPanel(api, 'validacion', {
    referencePanel: 'actividad',
    direction: 'within',
  });
  addStudioPanel(api, 'historial', {
    referencePanel: 'actividad',
    direction: 'within',
  });
  addStudioPanel(api, 'ia', {
    referencePanel: 'actividad',
    direction: 'within',
  });

  try {
    pJer.group?.api.setSize({ width: 256 });
    pProp.group?.api.setSize({ width: 320 });
    pAct.group?.api.setSize({ height: 220 });
  } catch {
    // Ignore sizing errors before layout measurement
  }
  pProp.api.setActive();
  pAct.api.setActive();
}

export function applyEscenaPropsLeftLayout(api: DockviewApi): void {
  api.clear();
  const pProp = addStudioPanel(api, 'propiedades', { initialWidth: 320 });
  addStudioPanel(api, 'anadir', {
    referencePanel: 'propiedades',
    direction: 'within',
  });
  addStudioPanel(api, 'mapa', { referencePanel: 'propiedades', direction: 'right' });
  const pJer = addStudioPanel(api, 'jerarquia', {
    referencePanel: 'mapa',
    direction: 'right',
    initialWidth: 256,
  });
  const pAct = addStudioPanel(api, 'actividad', {
    referencePanel: 'mapa',
    direction: 'below',
    initialHeight: 220,
  });
  addStudioPanel(api, 'validacion', {
    referencePanel: 'actividad',
    direction: 'within',
  });
  addStudioPanel(api, 'historial', {
    referencePanel: 'actividad',
    direction: 'within',
  });
  addStudioPanel(api, 'ia', {
    referencePanel: 'actividad',
    direction: 'within',
  });

  try {
    pProp.group?.api.setSize({ width: 320 });
    pJer.group?.api.setSize({ width: 256 });
    pAct.group?.api.setSize({ height: 220 });
  } catch {
    // Ignore sizing errors
  }
  pProp.api.setActive();
  pAct.api.setActive();
}

export function applyRodajeFactoryLayout(api: DockviewApi): void {
  api.clear();
  const pCam = addStudioPanel(api, 'camaras', { initialWidth: 256 });
  addStudioPanel(api, 'tomas', {
    referencePanel: 'camaras',
    direction: 'within',
  });
  addStudioPanel(api, 'mapa', { referencePanel: 'camaras', direction: 'right' });
  const pPrep = addStudioPanel(api, 'preparacion', {
    referencePanel: 'mapa',
    direction: 'right',
    initialWidth: 320,
  });
  addStudioPanel(api, 'propiedades', {
    referencePanel: 'preparacion',
    direction: 'within',
  });
  const pAct = addStudioPanel(api, 'actividad', {
    referencePanel: 'mapa',
    direction: 'below',
    initialHeight: 220,
  });
  addStudioPanel(api, 'vista-previa', {
    referencePanel: 'actividad',
    direction: 'within',
  });

  try {
    pCam.group?.api.setSize({ width: 256 });
    pPrep.group?.api.setSize({ width: 320 });
    pAct.group?.api.setSize({ height: 220 });
  } catch {
    // Ignore sizing errors
  }
  pCam.api.setActive();
  pPrep.api.setActive();
  pAct.api.setActive();
}

export function applyRodajePropsLeftLayout(api: DockviewApi): void {
  api.clear();
  const pPrep = addStudioPanel(api, 'preparacion', { initialWidth: 320 });
  addStudioPanel(api, 'propiedades', {
    referencePanel: 'preparacion',
    direction: 'within',
  });
  addStudioPanel(api, 'mapa', { referencePanel: 'preparacion', direction: 'right' });
  const pCam = addStudioPanel(api, 'camaras', {
    referencePanel: 'mapa',
    direction: 'right',
    initialWidth: 256,
  });
  addStudioPanel(api, 'tomas', {
    referencePanel: 'camaras',
    direction: 'within',
  });
  const pAct = addStudioPanel(api, 'actividad', {
    referencePanel: 'mapa',
    direction: 'below',
    initialHeight: 220,
  });
  addStudioPanel(api, 'vista-previa', {
    referencePanel: 'actividad',
    direction: 'within',
  });

  try {
    pPrep.group?.api.setSize({ width: 320 });
    pCam.group?.api.setSize({ width: 256 });
    pAct.group?.api.setSize({ height: 220 });
  } catch {
    // Ignore sizing errors
  }
  pPrep.api.setActive();
  pCam.api.setActive();
  pAct.api.setActive();
}

export function applyFactoryLayoutForMode(api: DockviewApi, mode: ModeName): void {
  if (mode === 'escena') {
    applyEscenaFactoryLayout(api);
  } else {
    applyRodajeFactoryLayout(api);
  }
}

export function applyPropsLeftLayoutForMode(api: DockviewApi, mode: ModeName): void {
  if (mode === 'escena') {
    applyEscenaPropsLeftLayout(api);
  } else {
    applyRodajePropsLeftLayout(api);
  }
}

export function openOrFocusPanel(api: DockviewApi, mode: ModeName, id: StudioPanelId): void {
  const allowed = getAllowedPanelsForMode(mode);
  if (!allowed.includes(id)) return;
  const existing = api.getPanel(id);
  if (existing) {
    existing.api.setActive();
    return;
  }

  // Try factory companions first
  const companionMap: Partial<Record<StudioPanelId, { ref: StudioPanelId; dir: 'within' | 'left' | 'right' | 'below' }>> = {
    anadir: { ref: 'propiedades', dir: 'within' },
    propiedades: { ref: 'anadir', dir: 'within' },
    validacion: { ref: 'actividad', dir: 'within' },
    historial: { ref: 'actividad', dir: 'within' },
    ia: { ref: 'actividad', dir: 'within' },
    actividad: { ref: 'validacion', dir: 'within' },
    tomas: { ref: 'camaras', dir: 'within' },
    camaras: { ref: 'tomas', dir: 'within' },
    preparacion: { ref: 'propiedades', dir: 'within' },
    'vista-previa': { ref: 'actividad', dir: 'within' },
    jerarquia: { ref: 'mapa', dir: 'left' },
  };

  const comp = companionMap[id];
  if (comp && api.getPanel(comp.ref)) {
    const p = addStudioPanel(api, id, { referencePanel: comp.ref, direction: comp.dir });
    p.api.setActive();
    return;
  }

  // Fallback: largest group or simple add
  let largestPanelId: StudioPanelId | undefined;
  let maxArea = -1;
  for (const p of api.panels) {
    const area = (p.api.width || 1) * (p.api.height || 1);
    if (area > maxArea) {
      maxArea = area;
      largestPanelId = p.id as StudioPanelId;
    }
  }

  const p = addStudioPanel(
    api,
    id,
    largestPanelId ? { referencePanel: largestPanelId, direction: 'within' } : undefined
  );
  p.api.setActive();
}

export function toggleStudioPanel(api: DockviewApi, mode: ModeName, id: StudioPanelId): void {
  const existing = api.getPanel(id);
  if (existing) {
    api.removePanel(existing);
  } else {
    openOrFocusPanel(api, mode, id);
  }
}
