import { useEffect, useState } from 'react';
import { SceneCamera, TakeError, TakeLiveSnapshot, TakeLiveTake } from '../types';
import { fetchTakeLive, goTake, prepareTake, stopTake, useStudioStore } from '../store';
import { fmt1 } from './CamerasPanel';

const LIVE_STATES = new Set(['preparando', 'armada', 'rodando']);

const BAD_LABELS: Record<string, string> = {
  scene: 'escena distinta',
  marks: 'actores fuera de marca',
  wardrobe: 'vestuario distinto',
  env: 'hora o clima distintos',
  director: 'sin director',
};

function eligibleCameras(cameras: SceneCamera[]): SceneCamera[] {
  return cameras.filter((c) => (c.keys ?? []).length >= 2);
}

function camName(cameras: SceneCamera[], camId: string): string {
  const named = cameras.find((c) => c.id === camId);
  return named ? named.name : camId;
}

function takeErrorText(error: TakeError): string {
  if (error.code === 'no_director') return 'Tu juego no está conectado';
  if (error.code === 'scene_not_observed') return 'Aplica la escena antes de preparar';
  if (error.code === 'take_busy') return 'Ya hay una toma en curso';
  return `No se pudo: ${error.msg}`;
}

function fallidaText(take: TakeLiveTake): string {
  if (take.reason === 'checks') {
    const parts = (take.bad ?? []).map((n) => BAD_LABELS[n] ?? n);
    return `No está lista: ${parts.join(', ')}`;
  }
  return `Falló (${take.reason ?? ''})`;
}

export function takeEstadoText(
  error: TakeError | null,
  live: TakeLiveSnapshot | null,
  cameras: SceneCamera[]
): string {
  if (error) return takeErrorText(error);
  const take = live?.take ?? null;
  if (!take) return 'Sin tomas todavía';
  const nombre = camName(cameras, take.cam_id);
  switch (take.state) {
    case 'preparando':
      return `Preparando ${nombre}`;
    case 'armada':
      return `Lista para rodar ${nombre}`;
    case 'rodando':
      return `Rodando ${nombre} · ${fmt1(take.t_ms / 1000)} / ${fmt1(take.dur_ms / 1000)} s`;
    case 'terminada':
      return 'Terminada';
    case 'parada':
      if (take.origin === 'web') return 'Parada desde la web';
      if (take.origin === 'juego') return 'Parada con la tecla del juego';
      if (take.origin === 'hombre_muerto') return 'Parada por hombre muerto';
      return 'Parada desde la web';
    case 'fallida':
      return fallidaText(take);
    default:
      return 'Sin tomas todavía';
  }
}

export function TakesPanel() {
  const { doc, takeLive, takeError } = useStudioStore();
  const cameras = doc?.cameras ?? [];
  const eligible = eligibleCameras(cameras);
  const [camId, setCamId] = useState('');
  const chosen = eligible.some((c) => c.id === camId) ? camId : eligible[0]?.id ?? '';
  const take = takeLive?.take ?? null;
  const viva = take ? LIVE_STATES.has(take.state) : false;

  useEffect(() => {
    void fetchTakeLive();
    const id = window.setInterval(() => {
      void fetchTakeLive();
    }, 500);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="panel" data-panel="tomas">
      <div className="panel-header">
        <span>Tomas</span>
      </div>
      <div className="panel-subbar">
        <select
          id="take-cam"
          disabled={eligible.length === 0}
          value={chosen}
          onChange={(e) => setCamId(e.target.value)}
        >
          {eligible.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn sm"
          id="take-prepare"
          disabled={!chosen || viva}
          onClick={() => {
            if (!chosen) return;
            void prepareTake(chosen);
          }}
        >
          Preparar
        </button>
        <button
          type="button"
          className="btn sm primary"
          id="take-go"
          disabled={!take || take.state !== 'armada'}
          onClick={() => {
            if (!take) return;
            void goTake(take.take_id);
          }}
        >
          Rodar
        </button>
        <button
          type="button"
          className="btn sm"
          id="take-stop"
          disabled={!viva || !take}
          onClick={() => {
            if (!take) return;
            void stopTake(take.take_id);
          }}
        >
          Parar
        </button>
      </div>
      {eligible.length === 0 ? (
        <div data-take-vacio>Crea una cámara con un camino para rodar.</div>
      ) : null}
      <div className="worldline" data-take-estado>
        {takeEstadoText(takeError, takeLive, cameras)}
      </div>
    </div>
  );
}
