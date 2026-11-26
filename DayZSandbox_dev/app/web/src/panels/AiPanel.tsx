import { useState } from 'react';
import {
  aiLightText,
  approveProposal,
  batchLabel,
  changeCount,
  disconnectAi,
  dismissProposal,
  formatAgo,
  isInverse,
  revertBatch,
  setAiPaused,
  undoneBatches,
  useCoedit,
} from '../coedit';
import { useStudioStore } from '../store';

// Pestaña IA (F6-web parte 2 §4.2): estado y pausa, propuesta de aplicar y tandas de la IA.
export function AiPanel() {
  const st = useStudioStore();
  const co = useCoedit();
  const now = performance.now();
  const wall = Date.now();
  const paused = co.view?.paused === true;
  const revoked = co.view?.revoked === true;
  const [confirming, setConfirming] = useState(false);
  const busy = st.sinBackend || co.pausing || co.view === null;
  const stateText = aiLightText(st.sinBackend, co, now);
  const undone = undoneBatches(co.batches);
  const aiBatches = co.batches
    .filter((b) => b.author?.role === 'ai' && !isInverse(b))
    .slice()
    .reverse();
  const p = co.proposal;
  const curRev = st.docInfo?.rev ?? null;
  const proposalStale = p !== null && curRev !== null && curRev !== p.rev;

  return (
    <div className="panel" data-panel="ia">
      <div className={`ai-head${paused ? ' paused' : ''}`}>
        <span className="who">
          <span className="ai-dot" aria-hidden="true" />
          IA co-editora <em>{stateText}</em>
        </span>
        <span className="desc">
          {revoked
            ? 'La IA está desconectada: su clave no vale hasta que reinicies el backend.'
            : paused
              ? 'La IA está en pausa: no cambia nada hasta que la reanudes.'
              : 'La IA edita el mismo borrador que tú. Si tocáis lo mismo, se queda lo tuyo.'}
        </span>
        <span className="grow" />
        {revoked ? null : confirming ? (
          <>
            <span className="desc">¿Desconectar hasta reiniciar el backend?</span>
            <button
              type="button"
              className="btn sm"
              disabled={busy}
              onClick={() => {
                setConfirming(false);
                void disconnectAi();
              }}
            >
              Sí, desconectar
            </button>
            <button type="button" className="btn sm" onClick={() => setConfirming(false)}>
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="btn sm"
              disabled={busy}
              onClick={() => void setAiPaused(!paused)}
            >
              {paused ? 'Reanudar IA' : 'Pausar IA'}
            </button>
            <button type="button" className="btn sm" disabled={busy} onClick={() => setConfirming(true)}>
              Desconectar
            </button>
          </>
        )}
      </div>

      {p ? (
        <div className="ai-prop" data-testid="propuesta-ia">
          <span>
            <b>La IA propone aplicar la revisión {p.rev}.</b> No se manda nada al juego hasta que lo
            apruebes.
          </span>
          {proposalStale ? (
            <span className="ai-stale">
              La escena cambió desde la propuesta (rev {p.rev} → rev {curRev}). Revísala y aplica desde
              arriba.
            </span>
          ) : null}
          {co.proposalError ? (
            <span className="ai-err" role="alert">
              {co.proposalError.code}
              {co.proposalError.msg ? `: ${co.proposalError.msg}` : ''}
            </span>
          ) : null}
          <span className="ai-prop-actions">
            <button
              type="button"
              className="btn sm"
              disabled={proposalStale || st.sinBackend || co.approving}
              onClick={() => void approveProposal()}
            >
              Aprobar y aplicar rev {p.rev}
            </button>
            <button type="button" className="btn sm" onClick={() => dismissProposal()}>
              Descartar
            </button>
          </span>
        </div>
      ) : null}

      <div className="ai-list" data-testid="tandas-ia">
        {aiBatches.length === 0 ? (
          <div className="empty">
            <p>La IA todavía no ha cambiado nada.</p>
          </div>
        ) : (
          aiBatches.map((b) => {
            const isUndone = undone.has(b.batch);
            const label = batchLabel(b);
            const n = changeCount(b);
            return (
              <div key={b.batch} className={`ai-row${isUndone ? ' off' : ''}`} data-batch={b.batch}>
                <span className="ai-dot" aria-hidden="true" />
                <span className="op">
                  <b>{label}</b>
                  <small>
                    {n === 1 ? '1 cambio' : `${n} cambios`}
                    {isUndone ? ' · deshecha' : ''}
                  </small>
                </span>
                <span className="age">{formatAgo(wall - b.at_ms)}</span>
                {isUndone ? (
                  <span />
                ) : (
                  <button
                    type="button"
                    className="btn sm"
                    aria-label={`Deshacer la tanda «${label}»`}
                    disabled={st.sinBackend || co.reverting !== null}
                    onClick={() => void revertBatch(b.batch)}
                  >
                    Deshacer tanda
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
