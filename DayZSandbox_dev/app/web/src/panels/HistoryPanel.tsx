import { useState } from 'react';
import { batchLabel, formatAgo, undoneBatches, useCoedit } from '../coedit';

type Filter = 'todas' | 'tuyas' | 'ia';

// Historial (F6-web parte 2 §4.4): todas las tandas, de los dos autores, en solo lectura.
export function HistoryPanel() {
  const co = useCoedit();
  const [filter, setFilter] = useState<Filter>('todas');
  const wall = Date.now();
  const undone = undoneBatches(co.batches);
  const rows = co.batches
    .filter((b) =>
      filter === 'todas' ? true : filter === 'ia' ? b.author?.role === 'ai' : b.author?.role !== 'ai'
    )
    .slice()
    .reverse();

  const pill = (id: Filter, text: string) => (
    <button
      type="button"
      className={`pill ${filter === id ? 'active' : ''}`}
      aria-pressed={filter === id}
      onClick={() => setFilter(id)}
    >
      {text}
    </button>
  );

  return (
    <div className="panel" data-panel="historial">
      <div className="panel-subbar">
        <span className="meta">Historial</span>
        <div className="spacer" />
        <div role="group" aria-label="Autor" className="pills">
          {pill('todas', 'Todas')}
          {pill('tuyas', 'Tuyas')}
          {pill('ia', 'IA')}
        </div>
      </div>
      {co.historyGap ? (
        <div className="hist-note">
          Las tandas de antes no están disponibles (el backend se reinició o quedan fuera del horizonte).
        </div>
      ) : null}
      <div className="hist-list">
        {rows.length === 0 ? (
          <div className="empty">
            <p>Todavía no hay cambios en esta sesión del backend.</p>
          </div>
        ) : (
          rows.map((b) => {
            const ai = b.author?.role === 'ai';
            const isUndone = undone.has(b.batch);
            const partial = Array.isArray(b.partial) && b.partial.length > 0;
            return (
              <div
                key={b.batch}
                className={`hrow${isUndone ? ' off' : ''}`}
                data-batch={b.batch}
                data-autor={ai ? 'ai' : 'human'}
                title={
                  partial
                    ? b.partial.map((x) => `${x.target} · ${x.field}`).join(', ')
                    : undefined
                }
              >
                <span className="rv">r{b.rev}</span>
                <span className="lbl">
                  {batchLabel(b)}
                  {isUndone ? ' · deshecha' : ''}
                  {partial ? ' · parcial' : ''}
                </span>
                <span className={`who${ai ? ' ai' : ''}`}>
                  {ai ? <span className="ai-dot" aria-hidden="true" /> : null}
                  {ai ? 'IA' : 'Tú'}
                </span>
                <span className="age">{formatAgo(wall - b.at_ms)}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
