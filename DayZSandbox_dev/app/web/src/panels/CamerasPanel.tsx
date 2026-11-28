import { useEffect } from 'react';
import { CameraLiveSnapshot, CameraPlayError, SceneCamera } from '../types';
import {
  commitSceneOps,
  fetchCameraLive,
  getDockviewApi,
  playCamera,
  setState,
  stopCamera,
  useStudioStore,
} from '../store';
import { openOrFocusPanel } from '../layout';

const DEFAULT_KEY = {
  t: 0,
  x: 7680,
  y: 2,
  z: 7680,
  yaw: 0,
  pitch: 0,
  fov: 50,
  focus: 10,
};

export function fmt1(n: number): string {
  return n.toFixed(1).replace('.', ',');
}

function cameraSummary(cam: SceneCamera): string {
  const keys = cam.keys ?? [];
  if (keys.length <= 1) return 'Fija';
  const lastT = keys[keys.length - 1]?.t ?? 0;
  return `Camino · ${keys.length} claves · ${fmt1(lastT)} s`;
}

export function juegoLabel(
  error: CameraPlayError | null,
  live: CameraLiveSnapshot | null,
  cameras: SceneCamera[]
): string {
  if (error) {
    if (error.code === 'client_not_in_game') return 'Tu juego no está conectado';
    if (error.code === 'camera_busy') return 'Hay una orden de cámara en curso';
    return `No se pudo: ${error.msg}`;
  }
  const last = live?.last;
  if (last && (last.status === 'rejected' || last.status === 'error')) {
    return `El juego no la aceptó (${last.reason})`;
  }
  if (last && last.status === 'dropped') return 'La orden no llegó al juego';
  const cam = live?.cam;
  if (!cam || cam.active === 0) return 'Sin cámara del estudio en el juego';
  const named = cameras.find((c) => c.id === cam.cam_id);
  const nombre = named ? named.name : cam.cam_id;
  if (cam.playing === 1) {
    return `Reproduciendo ${nombre} · ${fmt1(cam.t_ms / 1000)} / ${fmt1(cam.dur_ms / 1000)} s`;
  }
  return `Quieta en ${nombre}`;
}

export function CamerasPanel() {
  const { doc, selectedIds, sinBackend, mode, camLive, camPlayError } = useStudioStore();
  const cameras = doc?.cameras ?? [];
  const selectedCam =
    selectedIds.length === 1 ? cameras.find((c) => c.id === selectedIds[0]) : undefined;

  useEffect(() => {
    void fetchCameraLive();
    const id = window.setInterval(() => {
      void fetchCameraLive();
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  const selectCam = (id: string) => {
    setState({ selectedIds: [id] });
    const api = getDockviewApi();
    if (api) openOrFocusPanel(api, mode, 'propiedades');
  };

  const addCamera = () => {
    if (sinBackend || !doc) return;
    const n = doc.next.cam;
    void commitSceneOps('Nueva cámara', [
      {
        name: 'camera.add',
        args: { name: `Cámara ${n}`, keys: [{ ...DEFAULT_KEY }] },
      },
    ]);
  };

  return (
    <div className="panel" data-panel="camaras">
      <div className="panel-header">
        <span>Cámaras</span>
      </div>
      <div className="panel-subbar">
        <button type="button" className="btn sm" id="cam-new" disabled={sinBackend} onClick={addCamera}>
          Nueva cámara
        </button>
        <button
          type="button"
          className="btn sm primary"
          id="cam-play"
          disabled={sinBackend || !selectedCam}
          onClick={() => {
            if (!selectedCam) return;
            void playCamera(selectedCam.id);
          }}
        >
          Reproducir en el juego
        </button>
        <button
          type="button"
          className="btn sm"
          id="cam-stop"
          disabled={sinBackend}
          onClick={() => {
            void stopCamera();
          }}
        >
          Parar la cámara
        </button>
      </div>
      <div className="worldline" data-cam-juego>
        {juegoLabel(camPlayError, camLive, cameras)}
      </div>
      <div className="panel-body">
        {cameras.length === 0 ? (
          <div className="empty">
            <p>Todavía no hay cámaras.</p>
          </div>
        ) : (
          cameras.map((cam) => {
            const selected = selectedIds.length === 1 && selectedIds[0] === cam.id;
            return (
              <button
                key={cam.id}
                type="button"
                className="trow"
                data-cam={cam.id}
                aria-selected={selected}
                onClick={() => selectCam(cam.id)}
              >
                <span className="name">{cam.name}</span>
                <span className="meta">{cameraSummary(cam)}</span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
