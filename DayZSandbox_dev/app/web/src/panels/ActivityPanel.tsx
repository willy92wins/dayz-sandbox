import React from 'react';
import { StatusStateIcon } from '../icons';
import {
  formatAge,
  isKnownState,
  opNumber,
  setState,
  stateLabel,
  useStudioStore,
} from '../store';

export function ActivityPanel() {
  const { rows, activityFilter, sinBackend } = useStudioStore();

  const sortedRows = [...rows].sort((a, b) => opNumber(b.op_id) - opNumber(a.op_id));

  const filteredRows = sortedRows.filter((row) => {
    if (activityFilter === 'en-curso') {
      return row.state === 'pendiente' || row.state === 'ejecutando';
    }
    if (activityFilter === 'fallos') {
      return row.state === 'fallido' || row.state === 'parcial';
    }
    return true;
  });

  return (
    <div className="panel" data-panel="actividad">
      <div className="panel-subbar">
        <span className="meta">
          {sinBackend ? 'Actividad · lo último que se supo' : 'Actividad'}
        </span>
        <div className="spacer" />
        <button
          type="button"
          className={`pill ${activityFilter === 'todas' ? 'active' : ''}`}
          aria-pressed={activityFilter === 'todas'}
          onClick={() => setState({ activityFilter: 'todas' })}
        >
          Todas
        </button>
        <button
          type="button"
          className={`pill ${activityFilter === 'en-curso' ? 'active' : ''}`}
          aria-pressed={activityFilter === 'en-curso'}
          onClick={() => setState({ activityFilter: 'en-curso' })}
        >
          En curso
        </button>
        <button
          type="button"
          className={`pill ${activityFilter === 'fallos' ? 'active' : ''}`}
          aria-pressed={activityFilter === 'fallos'}
          onClick={() => setState({ activityFilter: 'fallos' })}
        >
          Fallos
        </button>
      </div>
      <div className="act-wrap">
        <table className="act-table" aria-label="Cola de operaciones">
          <thead>
            <tr>
              <th style={{ width: '78px' }}>Orden</th>
              <th style={{ width: '108px' }}>Revisión</th>
              <th style={{ width: '116px' }}>Estado</th>
              <th style={{ width: '110px' }}>Edad</th>
              <th style={{ width: '76px' }}>Origen</th>
              <th>Motivo</th>
              <th>Operación</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row) => {
              const known = isKnownState(row.state);
              const chipClass = known ? `chip ${row.state}` : 'chip';
              const operation = row.verb
                ? row.verb === 'scene.reset'
                  ? 'Quitar del juego'
                  : row.verb
                : 'Aplicar';
              return (
                <tr key={row.op_id} data-op-id={row.op_id}>
                  <td>{row.op_id}</td>
                  <td>
                    {row.hash
                      ? `${row.rev ?? ''} ${row.hash.slice(0, 8)}`
                      : `${row.rev ?? ''}`}
                  </td>
                  <td>
                    <span className={chipClass}>
                      <StatusStateIcon state={row.state} />
                      {stateLabel(row.state)}
                    </span>
                  </td>
                  <td>{formatAge(row)}</td>
                  <td>{row.origin ?? '—'}</td>
                  <td className="reason-cell">{row.reason ? row.reason : '—'}</td>
                  <td className="op-cell">{operation}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
