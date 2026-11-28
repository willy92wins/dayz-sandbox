import React, { useRef } from 'react';
import { EntityKind } from '../types';
import { KindGlyph, KNOWN_CLASS_NAMES } from '../icons';
import { setFlash, setState, useStudioStore } from '../store';

const TABS: readonly {
  kind: EntityKind;
  label: string;
  singular: string;
  disabled?: boolean;
}[] = [
  { kind: 'objeto', label: 'Objetos', singular: 'Objeto' },
  { kind: 'infectado', label: 'Infectados', singular: 'Infectado' },
  { kind: 'animal', label: 'Animales', singular: 'Animal' },
  { kind: 'actor', label: 'Actores', singular: 'Actor' },
];

export function AddPanel() {
  const {
    doc,
    catalog,
    addCategory,
    addQuery,
    previewItem,
    placingItem,
    sinBackend,
  } = useStudioStore();

  const listRef = useRef<HTMLDivElement | null>(null);

  const entities = doc?.entities ?? [];
  const classesForKind = catalog?.classes?.[addCategory] ?? [];
  const q = addQuery.trim().toLowerCase();

  const filteredClasses = classesForKind.filter((cls) => {
    if (!q) return true;
    const friendly = (KNOWN_CLASS_NAMES[cls] ?? '').toLowerCase();
    return cls.toLowerCase().includes(q) || friendly.includes(q);
  });

  const currentCount = entities.filter((e) => e.kind === addCategory).length;
  const currentCap = catalog?.caps?.[addCategory];
  const atCap = typeof currentCap === 'number' && currentCount >= currentCap;

  const activePreview =
    previewItem && previewItem.kind === addCategory
      ? previewItem
      : filteredClasses[0]
      ? { kind: addCategory, cls: filteredClasses[0] }
      : classesForKind[0]
      ? { kind: addCategory, cls: classesForKind[0] }
      : null;

  const focusItemByIndex = (idx: number) => {
    if (!listRef.current) return;
    const items = listRef.current.querySelectorAll<HTMLElement>('[data-cls]');
    if (idx >= 0 && idx < items.length) {
      items[idx].focus();
    }
  };

  const handleSelectCategory = (kind: EntityKind) => {
    const firstCls = catalog?.classes?.[kind]?.[0] ?? null;
    setState({
      addCategory: kind,
      placingItem: null,
      previewItem: firstCls ? { kind, cls: firstCls } : null,
    });
  };

  const noWardrobes =
    addCategory === 'actor' && (catalog?.wardrobes?.length ?? 0) === 0;

  const handleChooseClass = (cls: string) => {
    if (sinBackend) return;
    if (noWardrobes) return;
    if (atCap) {
      setFlash(`Tope de ${addCategory} alcanzado (${currentCount} / ${currentCap})`);
      return;
    }
    setState({
      placingItem: { kind: addCategory, cls },
      previewItem: { kind: addCategory, cls },
    });
  };

  const handleItemKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, idx: number, cls: string) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      focusItemByIndex(Math.min(filteredClasses.length - 1, idx + 1));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (idx === 0) {
        document.getElementById('libq')?.focus();
      } else {
        focusItemByIndex(idx - 1);
      }
      return;
    }
    if (e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      e.stopPropagation();
      handleChooseClass(cls);
      return;
    }
    if (e.key === 'Enter') {
      // Prevent native button click on Enter so only the global `colocar` shortcut handles Enter when placingItem is set
      e.preventDefault();
    }
  };

  const previewMetaLabel =
    TABS.find((t) => t.kind === activePreview?.kind)?.singular ??
    activePreview?.kind ??
    '';

  return (
    <div className="panel" data-panel="anadir">
      <div className="lib-tabs" role="tablist" aria-label="Tipo">
        {TABS.map((t) => {
          const count = catalog?.classes?.[t.kind]?.length ?? 0;
          const isSelected = addCategory === t.kind;
          return (
            <button
              key={t.kind}
              type="button"
              role="tab"
              className="lib-tab"
              aria-selected={isSelected}
              disabled={t.disabled}
              title={t.disabled ? 'Llega con F3' : undefined}
              onClick={() => {
                if (!t.disabled) handleSelectCategory(t.kind);
              }}
            >
              {t.label} {count}
            </button>
          );
        })}
      </div>

      <div className="panel-subbar">
        <input
          id="libq"
          type="search"
          className="search"
          placeholder="Buscar por nombre o clase"
          aria-label="Buscar en el catálogo"
          value={addQuery}
          disabled={sinBackend}
          onChange={(e) => setState({ addQuery: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              focusItemByIndex(0);
            } else if (e.key === 'Enter') {
              e.preventDefault();
              e.stopPropagation();
            }
          }}
        />
      </div>

      {placingItem ? (
        <div className="lib-placing-bar" role="status">
          Colocando {placingItem.cls} · Intro para colocar, Esc para cancelar
        </div>
      ) : null}

      {atCap ? (
        <div className="lib-cap-note" role="status">
          Tope de {addCategory} alcanzado ({currentCount} / {currentCap})
        </div>
      ) : null}

      <div className="panel-body">
        {filteredClasses.length === 0 ? (
          <div className="empty">
            <p>
              <strong>Nada con «{addQuery}»</strong>
            </p>
            <button
              type="button"
              className="btn sm"
              onClick={() => {
                setState({ addQuery: '' });
                document.getElementById('libq')?.focus();
              }}
            >
              Limpiar búsqueda
            </button>
          </div>
        ) : (
          <div ref={listRef} className="lib-list">
            {filteredClasses.map((cls, idx) => {
              const isPlacing =
                placingItem?.kind === addCategory && placingItem?.cls === cls;
              const friendly = KNOWN_CLASS_NAMES[cls];
              const isRowDisabled = atCap || sinBackend || noWardrobes;
              return (
                <button
                  key={cls}
                  type="button"
                  className="lib-item"
                  data-cls={cls}
                  aria-pressed={isPlacing}
                  aria-disabled={isRowDisabled ? 'true' : undefined}
                  onMouseEnter={() =>
                    setState({ previewItem: { kind: addCategory, cls } })
                  }
                  onFocus={() =>
                    setState({ previewItem: { kind: addCategory, cls } })
                  }
                  onClick={() => handleChooseClass(cls)}
                  onKeyDown={(e) => handleItemKeyDown(e, idx, cls)}
                >
                  <span className="lib-item-main">
                    <KindGlyph kind={addCategory} cls={cls} />
                    <span>{friendly ? `${friendly} (${cls})` : cls}</span>
                    {noWardrobes ? (
                      <span>El catálogo no tiene vestuarios</span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div id="libPrev" className="lib-preview">
        {activePreview ? (
          <>
            <div className="lib-preview-head">
              <KindGlyph kind={activePreview.kind} cls={activePreview.cls} />
              <span>
                {KNOWN_CLASS_NAMES[activePreview.cls] ?? activePreview.cls}
              </span>
              <span className="lib-item-cls">{activePreview.cls}</span>
              <span>· {previewMetaLabel}</span>
            </div>
            <div className="lib-preview-meta">
              Sin captura del juego todavía · Sin tamaño en el catálogo
            </div>
          </>
        ) : (
          <div className="lib-preview-meta">
            Sin captura del juego todavía · Sin tamaño en el catálogo
          </div>
        )}
      </div>

      <div className="budgets">
        <div className="budgets-title">Presupuesto · provisional</div>
        <div className="budgets-grid">
          {TABS.map((t) => {
            const c = entities.filter((e) => e.kind === t.kind).length;
            const cap = catalog?.caps?.[t.kind];
            return (
              <div key={t.kind} className="bmeter" data-budget={t.kind}>
                <div className="bmeter-top">
                  <span>{t.label}</span>
                  <b>
                    {c} / {cap ?? '—'}
                  </b>
                </div>
              </div>
            );
          })}
        </div>
        <div className="btotal">
          {entities.length} {entities.length === 1 ? 'entidad' : 'entidades'} · Tope
          total aún sin certificar
        </div>
      </div>
    </div>
  );
}
