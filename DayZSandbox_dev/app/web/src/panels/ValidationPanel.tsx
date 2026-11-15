import React from 'react';
import { openOrFocusPanel } from '../layout';
import { getDockviewApi, setState, useStudioStore } from '../store';
import { ValidationErrorItem } from '../types';

export function ValidationPanel() {
  const { validationErrors, doc, mode } = useStudioStore();

  const resolveTarget = (
    err: ValidationErrorItem
  ): {
    hasEntityPointer: boolean;
    targetId: string | null;
    field: string | null;
    exists: boolean;
  } => {
    if (err.pointer === '/entities') {
      return { hasEntityPointer: false, targetId: null, field: null, exists: false };
    }
    if (err.targetId === 'ambiente' || err.pointer.startsWith('/ambiente/')) {
      const f = err.field ?? (err.pointer.startsWith('/ambiente/') ? err.pointer.slice(10) : null);
      return {
        hasEntityPointer: true,
        targetId: 'ambiente',
        field: f,
        exists: Boolean(doc?.ambiente),
      };
    }
    if (err.targetId) {
      const found = Boolean(doc?.entities.some((e) => e.id === err.targetId));
      return {
        hasEntityPointer: true,
        targetId: err.targetId,
        field: err.field,
        exists: found,
      };
    }
    const m = /^\/entities\/(\d+)(?:\/(.+))?$/.exec(err.pointer);
    if (m) {
      const idx = parseInt(m[1], 10);
      const ent = doc?.entities[idx];
      return {
        hasEntityPointer: true,
        targetId: ent?.id ?? null,
        field: err.field ?? m[2] ?? null,
        exists: Boolean(ent),
      };
    }
    return { hasEntityPointer: false, targetId: null, field: null, exists: false };
  };

  const handleVer = (err: ValidationErrorItem) => {
    const { hasEntityPointer, targetId, field, exists } = resolveTarget(err);
    if (!hasEntityPointer || !exists || !targetId) {
      return;
    }
    const targetField = field ?? 'x';
    const api = getDockviewApi();
    if (api) {
      openOrFocusPanel(api, mode, 'propiedades');
    }
    // El foco lo pone Propiedades cuando ya se ha repintado con esta entidad (pendingFocusField).
    // Enfocar aquí #f-<campo> lo haría sobre el campo de la entidad que se veía antes, y su
    // préstamo se quedaría con la entidad equivocada (el campo nuevo, en solo lectura).
    setState({
      selectedIds: [targetId],
      pendingFocusField: { targetId, field: targetField },
    });
  };

  return (
    <div className="panel" data-panel="validacion">
      <div className="panel-subbar">
        <span className="meta">
          Validación · {validationErrors.length}{' '}
          {validationErrors.length === 1 ? 'aviso' : 'avisos'}
        </span>
      </div>
      <div className="panel-body">
        {validationErrors.length === 0 ? (
          <div className="empty-cta">
            <span className="meta">Sin avisos de validación activos.</span>
          </div>
        ) : (
          <ul className="val-list">
            {validationErrors.map((err) => {
              const { hasEntityPointer, exists } = resolveTarget(err);
              return (
                <li
                  key={err.id}
                  className="val-item"
                  data-error-pointer={err.pointer}
                >
                  <div className="val-item-head">
                    <span className="val-msg">{err.msg}</span>
                    {hasEntityPointer && (
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                        {!exists && <span className="meta">Ya no existe</span>}
                        <button
                          type="button"
                          className="btn"
                          onClick={() => handleVer(err)}
                        >
                          Ver
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="val-ptr">
                    <span>{err.code}</span> · <span>{err.pointer || '/'}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
