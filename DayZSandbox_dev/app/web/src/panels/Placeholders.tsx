import React from 'react';
import { StudioPanelId } from '../types';

export function PlaceholderPanel({ id }: { id: StudioPanelId }) {
  let content: React.ReactNode;
  if (id === 'mapa') {
    content = (
      <p>
        <strong>El mapa llega con S-mapa.</strong> Mientras tanto, coloca con Intro desde Añadir y
        escribe X y Z en Propiedades.
      </p>
    );
  } else if (id === 'historial') {
    content = (
      <p>
        <strong>El historial llega en la parte 2.</strong> Deshacer y Rehacer ya funcionan desde la
        barra de arriba.
      </p>
    );
  } else if (id === 'ia') {
    content = (
      <p>
        <strong>La pestaña de la IA llega en la parte 2.</strong>
      </p>
    );
  } else {
    content = (
      <p>
        <strong>Llega con F4 y F5.</strong> Aquí irán las cámaras, las tomas, la preparación y la
        vista previa del mapa.
      </p>
    );
  }

  return (
    <div className="panel" data-panel={id}>
      <div className="empty" data-hueco={id}>
        {content}
      </div>
    </div>
  );
}
