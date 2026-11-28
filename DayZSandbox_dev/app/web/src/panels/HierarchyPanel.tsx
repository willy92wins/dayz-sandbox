import React, { useRef } from 'react';
import { EntityKind, SceneEntity } from '../types';
import { KindGlyph } from '../icons';
import {
  getDockviewApi,
  setState,
  useStudioStore,
} from '../store';
import { openOrFocusPanel } from '../layout';
import { AI_FRESH_MS, formatAgo, useCoedit } from '../coedit';

const KIND_ORDER: readonly { kind: EntityKind; label: string }[] = [
  { kind: 'objeto', label: 'Objetos' },
  { kind: 'infectado', label: 'Infectados' },
  { kind: 'animal', label: 'Animales' },
  { kind: 'actor', label: 'Actores' },
];

export function HierarchyPanel() {
  const { doc, catalog, selectedIds, hierarchyQuery, mode } = useStudioStore();
  const { aiTouched } = useCoedit();
  const now = performance.now();
  const lastClickedIdRef = useRef<string | null>(null);
  const treeRef = useRef<HTMLDivElement | null>(null);

  const entities = doc?.entities ?? [];
  const q = hierarchyQuery.trim().toLowerCase();

  const matchesQuery = (e: SceneEntity): boolean => {
    if (!q) return true;
    return (
      e.name.toLowerCase().includes(q) ||
      e.cls.toLowerCase().includes(q) ||
      e.id.toLowerCase().includes(q)
    );
  };

  // Ordered visible entities matching the group order
  const orderedEntities: SceneEntity[] = [];
  for (const g of KIND_ORDER) {
    for (const e of entities) {
      if (e.kind === g.kind && matchesQuery(e)) {
        orderedEntities.push(e);
      }
    }
  }

  const allTreeItemIds = ['ambiente', ...orderedEntities.map((e) => e.id)];
  const activeRovingId =
    selectedIds.find((id) => allTreeItemIds.includes(id)) ?? allTreeItemIds[0] ?? 'ambiente';

  const focusTreeItem = (id: string) => {
    if (!treeRef.current) return;
    const el = treeRef.current.querySelector<HTMLElement>(
      `[data-tree-id="${CSS.escape(id)}"]`
    );
    if (el) el.focus();
  };

  const handleRowClick = (e: React.MouseEvent, id: string) => {
    if (id === 'ambiente') {
      lastClickedIdRef.current = 'ambiente';
      setState({ selectedIds: ['ambiente'] });
      return;
    }

    if (e.shiftKey && lastClickedIdRef.current && lastClickedIdRef.current !== 'ambiente') {
      const ids = orderedEntities.map((ent) => ent.id);
      const a = ids.indexOf(lastClickedIdRef.current);
      const b = ids.indexOf(id);
      if (a !== -1 && b !== -1) {
        const [lo, hi] = a <= b ? [a, b] : [b, a];
        const range = ids.slice(lo, hi + 1);
        setState({ selectedIds: range });
        return;
      }
    }

    if (e.ctrlKey || e.metaKey) {
      const withoutAmb = selectedIds.filter((x) => x !== 'ambiente');
      const exists = withoutAmb.includes(id);
      const next = exists ? withoutAmb.filter((x) => x !== id) : [...withoutAmb, id];
      lastClickedIdRef.current = id;
      setState({ selectedIds: next });
      return;
    }

    lastClickedIdRef.current = id;
    setState({ selectedIds: [id] });
  };

  const handleTreeKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      e.stopPropagation();
      if (allTreeItemIds.length === 0) return;
      const currentIdx = Math.max(0, allTreeItemIds.indexOf(activeRovingId));
      const nextIdx =
        e.key === 'ArrowDown'
          ? Math.min(allTreeItemIds.length - 1, currentIdx + 1)
          : Math.max(0, currentIdx - 1);
      const nextId = allTreeItemIds[nextIdx];
      lastClickedIdRef.current = nextId;
      setState({ selectedIds: [nextId] });
      focusTreeItem(nextId);
      return;
    }
    // Borrar, Seleccionar todo e Ir a las propiedades no se atienden aquí: los resuelve el mapa
    // común de atajos (App.tsx), que respeta las teclas reasignadas y las acciones sin tecla
    // (revisión de Sol, F02). Este manejador se queda solo con la navegación del árbol.
  };

  const handleOpenAddFirstObject = () => {
    const api = getDockviewApi();
    if (api) {
      openOrFocusPanel(api, mode, 'anadir');
    }
    window.setTimeout(() => {
      const qInput = document.getElementById('libq');
      qInput?.focus();
    }, 40);
  };

  const totalCount = entities.length;

  return (
    <div className="panel" data-panel="jerarquia">
      <div className="panel-header">
        <span>
          Jerarquía · {totalCount} {totalCount === 1 ? 'entidad' : 'entidades'}
        </span>
      </div>
      <div className="worldline">Sin lectura del juego</div>
      <div className="panel-subbar">
        <input
          type="search"
          className="search"
          placeholder="Buscar por nombre o clase"
          aria-label="Buscar por nombre o clase"
          value={hierarchyQuery}
          onChange={(e) => setState({ hierarchyQuery: e.target.value })}
        />
      </div>
      <div className="panel-body">
        {totalCount === 0 ? (
          <div className="empty">
            <p>
              <strong>Esta escena está vacía.</strong>
            </p>
            <button type="button" className="btn primary" onClick={handleOpenAddFirstObject}>
              Añade tu primer objeto
            </button>
          </div>
        ) : null}

        <div
          ref={treeRef}
          className="tree"
          role="tree"
          aria-label="Jerarquía"
          aria-multiselectable="true"
          onKeyDown={handleTreeKeyDown}
        >
          <div
            role="treeitem"
            className="trow"
            data-tree-id="ambiente"
            aria-selected={selectedIds.includes('ambiente')}
            tabIndex={activeRovingId === 'ambiente' ? 0 : -1}
            onClick={(e) => handleRowClick(e, 'ambiente')}
          >
            <KindGlyph kind="ambiente" />
            <span className="name">Ambiente</span>
          </div>

          {KIND_ORDER.map(({ kind, label }) => {
            const totalOfKind = entities.filter((e) => e.kind === kind).length;
            const cap = catalog?.caps?.[kind];
            const atCap = typeof cap === 'number' && totalOfKind >= cap;
            const groupEntities = entities.filter(
              (e) => e.kind === kind && matchesQuery(e)
            );
            return (
              <React.Fragment key={kind}>
                <div className="tgroup" role="presentation">
                  <span>{label}</span>
                  {typeof cap === 'number' ? (
                    <b className={atCap ? 'full' : undefined}>
                      {totalOfKind} / {cap}
                    </b>
                  ) : (
                    <span>{totalOfKind}</span>
                  )}
                </div>
                {groupEntities.map((ent) => {
                  const isSelected = selectedIds.includes(ent.id);
                  return (
                    <div
                      key={ent.id}
                      role="treeitem"
                      className="trow"
                      data-entity-id={ent.id}
                      data-tree-id={ent.id}
                      aria-selected={isSelected}
                      tabIndex={activeRovingId === ent.id ? 0 : -1}
                      onClick={(e) => handleRowClick(e, ent.id)}
                    >
                      <KindGlyph kind={ent.kind} cls={ent.cls} />
                      <span className="name">{ent.name}</span>
                      {aiTouched[ent.id] !== undefined && now - aiTouched[ent.id] < AI_FRESH_MS ? (
                        <span
                          className="ai-b"
                          data-ia-reciente
                          title="Cambiado por la IA hace un momento"
                        >
                          IA · {formatAgo(now - aiTouched[ent.id])}
                        </span>
                      ) : null}
                    </div>
                  );
                })}
              </React.Fragment>
            );
          })}

          <div className="tgroup" role="presentation">
            <span>Cámaras</span>
            <span>{(doc?.cameras ?? []).length === 0 ? 'Ninguna' : (doc?.cameras ?? []).length}</span>
          </div>
          {(doc?.cameras ?? []).map((cam) => {
            const isSelected = selectedIds.includes(cam.id);
            return (
              <div
                key={cam.id}
                role="treeitem"
                className="trow"
                data-cam-id={cam.id}
                aria-selected={isSelected}
                tabIndex={-1}
                onClick={() => {
                  lastClickedIdRef.current = cam.id;
                  setState({ selectedIds: [cam.id] });
                }}
              >
                <span className="name">{cam.name}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
