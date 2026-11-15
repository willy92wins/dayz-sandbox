export type ShortcutContext = 'escena' | 'toma' | 'global';

export interface ShortcutActionDef {
  id: string;
  name: string;
  def: string;
  ctx: ShortcutContext;
  mandatory: boolean;
}

export const ACTIONS: readonly ShortcutActionDef[] = [
  { id: 'colocar', name: 'Colocar lo elegido', def: 'Enter', ctx: 'escena', mandatory: true },
  { id: 'aplicar', name: 'Aplicar la escena', def: 'Ctrl+Enter', ctx: 'global', mandatory: true },
  { id: 'preparar', name: 'Preparar la toma', def: 'Shift+F9', ctx: 'toma', mandatory: true },
  { id: 'rodar', name: 'Rodar la toma armada', def: 'Enter', ctx: 'toma', mandatory: true },
  { id: 'parar', name: 'Parar la toma o desarmarla', def: 'Escape', ctx: 'toma', mandatory: true },
  { id: 'parar-espacio', name: 'Parar la toma que rueda', def: 'Space', ctx: 'toma', mandatory: false },
  { id: 'deshacer', name: 'Deshacer', def: 'Ctrl+Z', ctx: 'global', mandatory: false },
  { id: 'rehacer', name: 'Rehacer', def: 'Ctrl+Y', ctx: 'global', mandatory: false },
  { id: 'guardar', name: 'Guardar', def: 'Ctrl+S', ctx: 'global', mandatory: false },
  { id: 'borrar', name: 'Borrar lo seleccionado', def: 'Delete', ctx: 'escena', mandatory: false },
  { id: 'duplicar', name: 'Duplicar', def: 'Ctrl+J', ctx: 'escena', mandatory: false },
  { id: 'seleccionar-todo', name: 'Seleccionar todo', def: 'Ctrl+A', ctx: 'escena', mandatory: false },
  { id: 'ir-propiedades', name: 'Ir a las propiedades', def: 'Alt+Enter', ctx: 'escena', mandatory: false },
  { id: 'copiar-coordenadas', name: 'Copiar coordenadas', def: 'P', ctx: 'escena', mandatory: false },
  { id: 'modo-escena', name: 'Ir a Escena', def: '1', ctx: 'global', mandatory: false },
  { id: 'modo-rodaje', name: 'Ir a Rodaje', def: '2', ctx: 'global', mandatory: false },
];

export const BROWSER_RESERVED_COMBOS = new Set<string>([
  'Ctrl+N',
  'Ctrl+Shift+N',
  'Ctrl+T',
  'Ctrl+Shift+T',
  'Ctrl+W',
  'Ctrl+Shift+W',
  'Ctrl+Tab',
  'Ctrl+Shift+Tab',
  'Ctrl+PageUp',
  'Ctrl+PageDown',
  'Ctrl+L',
  'Ctrl+R',
  'Ctrl+Shift+R',
  'F5',
  'Ctrl+F5',
  'F6',
  'F10',
  'F11',
  'F12',
  'Ctrl+Shift+I',
  'Ctrl+Shift+J',
  'Alt+F4',
  'Tab',
  'Shift+Tab',
]);

const VALID_COMBO_RE =
  /^(Ctrl\+)?(Alt\+)?(Shift\+)?([A-Z0-9]|F([1-9]|1[0-2])|Enter|Escape|Delete|Space|Backspace|ArrowUp|ArrowDown|ArrowLeft|ArrowRight|Home|End|PageUp|PageDown|Tab)$/;

export function isValidCombo(combo: string): boolean {
  return VALID_COMBO_RE.test(combo);
}

export function contextsOverlap(a: ShortcutContext, b: ShortcutContext): boolean {
  return a === b || a === 'global' || b === 'global';
}

export function getDefaultKeymap(): Record<string, string | null> {
  const map: Record<string, string | null> = {};
  for (const a of ACTIONS) {
    map[a.id] = a.def;
  }
  return map;
}

export function keyLabel(k: string | null | undefined): string {
  if (!k) return 'Sin tecla';
  return k
    .split('+')
    .map((part) => {
      if (part === 'Shift') return 'Mayús';
      if (part === 'Enter') return 'Intro';
      if (part === 'Escape') return 'Esc';
      if (part === 'Delete') return 'Supr';
      if (part === 'Space') return 'Espacio';
      return part;
    })
    .join('+');
}

export function comboOf(e: KeyboardEvent): string | null {
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) {
    return null;
  }
  const parts: string[] = [];
  if (e.ctrlKey || e.metaKey) parts.push('Ctrl');
  if (e.altKey) parts.push('Alt');
  if (e.shiftKey) parts.push('Shift');
  let k = e.key;
  if (k === ' ') k = 'Space';
  else if (k.length === 1) k = k.toUpperCase();
  parts.push(k);
  return parts.join('+');
}

export function findConflict(
  keymap: Record<string, string | null>,
  actionId: string,
  combo: string
): ShortcutActionDef | null {
  const target = ACTIONS.find((a) => a.id === actionId);
  if (!target) return null;
  for (const other of ACTIONS) {
    if (other.id === actionId) continue;
    if (keymap[other.id] === combo && contextsOverlap(target.ctx, other.ctx)) {
      return other;
    }
  }
  return null;
}

export function sanitizeKeymap(raw: unknown): {
  keymap: Record<string, string | null>;
  corrected: boolean;
} {
  const defaults = getDefaultKeymap();
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    return { keymap: defaults, corrected: false };
  }
  const src = raw as Record<string, unknown>;
  const out: Record<string, string | null> = { ...defaults };
  let corrected = false;

  for (const action of ACTIONS) {
    if (!(action.id in src)) {
      out[action.id] = action.def;
      continue;
    }
    const val = src[action.id];
    if (val === null) {
      if (action.mandatory) {
        out[action.id] = action.def;
        corrected = true;
      } else {
        out[action.id] = null;
      }
      continue;
    }
    if (typeof val !== 'string' || !isValidCombo(val) || BROWSER_RESERVED_COMBOS.has(val)) {
      out[action.id] = action.def;
      corrected = true;
      continue;
    }
    out[action.id] = val;
  }

  // Choques entre contextos que se solapan: las acciones del choque que no tienen su tecla de serie
  // vuelven a ella. Reparar un choque puede crear otro (esa tecla de serie puede estar ocupada), así
  // que se repite hasta que no cambie nada (revisión de Sol, F09). Cada vuelta que cambia algo deja
  // una acción más en su tecla de serie, así que acaba; y solo toca las acciones de algún choque.
  for (let pass = 0; pass <= ACTIONS.length; pass++) {
    let changed = false;
    for (let i = 0; i < ACTIONS.length; i++) {
      for (let j = i + 1; j < ACTIONS.length; j++) {
        const a = ACTIONS[i];
        const b = ACTIONS[j];
        const ka = out[a.id];
        const kb = out[b.id];
        if (ka !== null && ka === kb && contextsOverlap(a.ctx, b.ctx)) {
          corrected = true;
          if (out[a.id] !== a.def) {
            out[a.id] = a.def;
            changed = true;
          }
          if (out[b.id] !== b.def) {
            out[b.id] = b.def;
            changed = true;
          }
        }
      }
    }
    if (!changed) break;
  }

  // Red de seguridad: el mapa de serie no tiene choques, así que esto no debería pasar nunca; si
  // pasara, se vuelve al mapa de serie entero.
  if (hasKeymapConflicts(out)) {
    return { keymap: { ...defaults }, corrected: true };
  }

  return { keymap: out, corrected };
}

export function hasKeymapConflicts(keymap: Record<string, string | null>): boolean {
  for (let i = 0; i < ACTIONS.length; i++) {
    for (let j = i + 1; j < ACTIONS.length; j++) {
      const a = ACTIONS[i];
      const b = ACTIONS[j];
      const ka = keymap[a.id];
      if (ka != null && ka === keymap[b.id] && contextsOverlap(a.ctx, b.ctx)) return true;
    }
  }
  return false;
}
