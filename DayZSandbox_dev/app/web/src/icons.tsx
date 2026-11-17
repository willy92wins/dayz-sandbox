import React from 'react';
import { EntityKind } from './types';

export const OBJ_PATHS: Record<string, string> = {
  autobus:
    'M-5.8 -4.6H5.8A1.2 1.2 0 0 1 7 -3.4V2.4H5.9A1.8 1.8 0 0 1 2.3 2.4H-2.3A1.8 1.8 0 0 1 -5.9 2.4H-7V-3.4A1.2 1.2 0 0 1 -5.8 -4.6Z M-5.6 -3.2h2.8v2.4h-2.8z M-1.4 -3.2h2.8v2.4h-2.8z M2.8 -3.2h2.8v2.4h-2.8z',
  coche:
    'M-7 2.4V0.2Q-7 -0.9 -5.8 -0.9H-4.3L-2.6 -3.9Q-2.4 -4.2 -2 -4.2H1.9Q2.3 -4.2 2.6 -3.9L4.6 -0.9H6Q7 -0.9 7 0.2V2.4H5.9A1.75 1.75 0 0 1 2.4 2.4H-2.4A1.75 1.75 0 0 1 -5.9 2.4Z M-3.3 -1.5L-2 -3.4H-0.5V-1.5Z M0.5 -1.5V-3.4H1.8L3.2 -1.5Z',
  camion:
    'M-7 -4.6H1.2V1.2H2.6V-2.6H5.2L7 -0.6V2.4H6.3A1.7 1.7 0 0 1 2.9 2.4H0.5A1.7 1.7 0 0 1 -2.9 2.4A1.7 1.7 0 0 1 -6.3 2.4H-7Z M3.4 -1.8H5L6.1 -0.4H3.4Z',
  contenedor:
    'M-6.8 -4H6.8V4H-6.8Z M-3.6 -2.6h1.2v5.2h-1.2z M-0.6 -2.6h1.2v5.2h-1.2z M2.4 -2.6h1.2v5.2h-1.2z',
  tienda: 'M0 -6.6L7 4.8H2.4L0 0.4L-2.4 4.8H-7Z',
  red: 'M-7 -1.2L-3.6 -5L0 -2.8L3.6 -5L7 -1.2L6 0.6L5 -0.4L4.2 0.6V5H3V0.6L2 -0.4L1 0.6L0 -0.4L-1 0.6L-2 -0.4L-3 0.6V5H-4.2V0.6L-5 -0.4L-6 0.6Z',
  hoguera:
    'M0 -7C2.2 -4.8 3.6 -3 3.6 -0.5C3.6 1.7 2 3 0 3C-2 3 -3.6 1.7 -3.6 -0.5C-3.6 -2.3 -2.5 -3.4 -1.6 -4.6C-1.3 -3.4 -0.8 -2.8 -0.2 -2.5C0.3 -4 0.4 -5.4 0 -7Z M-5.86 6.99L6.14 4.79L5.86 3.21L-6.14 5.41Z M-6.14 4.79L-1.58 5.62L-1.3 4.05L-5.86 3.21Z M1.3 6.15L5.86 6.99L6.14 5.41L1.58 4.58Z',
  bidon:
    'M-2.8 -6.6H2.8Q4 -6.6 4.1 -5.2L4.3 -2.9H-4.3L-4.1 -5.2Q-4 -6.6 -2.8 -6.6Z M-4.4 -1.5H4.4V1.5H-4.4Z M-4.3 2.9H4.3L4.1 5.2Q4 6.6 2.8 6.6H-2.8Q-4 6.6 -4.1 5.2Z',
  caja: 'M-5.4 -5.4H5.4V5.4H-5.4Z M-3.1 -3.95H3.1L0 -0.85Z M3.95 -3.1V3.1L0.85 0Z M3.1 3.95H-3.1L0 0.85Z M-3.95 3.1V-3.1L-0.85 0Z',
  foco: 'M-5.8 -5.2L0.4 -7L0.4 -1.6L-5.8 -3.4Z M2.1 -5.01L6.9 -5.81L6.7 -6.99L1.9 -6.19Z M2 -3.7L6.8 -3.7L6.8 -4.9L2 -4.9Z M1.9 -2.41L6.7 -1.61L6.9 -2.79L2.1 -3.59Z M-3.4 -2.7L-2.2 -2.35L-2.2 1L1.4 6.8L0 6.8L-2.2 3.2L-2.2 6.8L-3.4 6.8L-3.4 3.2L-5.6 6.8L-7 6.8L-3.4 1Z',
  generador:
    'M-4.9 -4.2H4.9Q5.8 -4.2 5.8 -3.3V2.1Q5.8 3 4.9 3H4.8V4.3H3.1V3H-3.1V4.3H-4.8V3H-4.9Q-5.8 3 -5.8 2.1V-3.3Q-5.8 -4.2 -4.9 -4.2Z M0.8 -3.1L-2.1 0.2H-0.3L-0.9 2.2L2.1 -0.9H0.3Z',
  generico:
    'M0 -6L5.2 -3.1L0 -0.2L-5.2 -3.1Z M-5.6 -2.2L-0.55 0.7V6.2L-5.6 3.3Z M5.6 -2.2V3.3L0.55 6.2V0.7Z',
};

const OBJ_CLASS_TO_TIPO: Record<string, string> = {
  Land_Wreck_Ikarus: 'autobus',
  Land_Wreck_Volha_Police: 'coche',
  Land_Wreck_Volha_Blue: 'coche',
  Land_Wreck_V3S: 'camion',
  Land_Container_1Bo: 'contenedor',
  Land_Container_1Aoh: 'contenedor',
  LargeTent: 'tienda',
  MediumTent: 'tienda',
  CarTent: 'tienda',
  CamoNet: 'red',
  Fireplace: 'hoguera',
  Barrel_Red: 'bidon',
  Barrel_Blue: 'bidon',
  Barrel_Green: 'bidon',
  Barrel_Yellow: 'bidon',
  WoodenCrate: 'caja',
  SeaChest: 'caja',
  Spotlight: 'foco',
  PowerGenerator: 'generador',
};

export const KNOWN_CLASS_NAMES: Record<string, string> = {
  Land_Wreck_Ikarus: 'Autobús Ikarus',
  Land_Wreck_Volha_Police: 'Volga de policía',
  Land_Wreck_Volha_Blue: 'Volga azul',
  Land_Wreck_V3S: 'Camión V3S',
  Land_Container_1Bo: 'Contenedor',
  Land_Container_1Aoh: 'Contenedor abierto',
  LargeTent: 'Tienda grande',
  MediumTent: 'Tienda mediana',
  CarTent: 'Toldo de coche',
  CamoNet: 'Red de camuflaje',
  Fireplace: 'Hoguera',
  Barrel_Red: 'Bidón rojo',
  Barrel_Blue: 'Bidón azul',
  Barrel_Green: 'Bidón verde',
  Barrel_Yellow: 'Bidón amarillo',
  WoodenCrate: 'Caja de madera',
  SeaChest: 'Baúl',
  Spotlight: 'Foco',
  PowerGenerator: 'Generador',
  ZmbM_FarmerFat_Brown: 'Granjero',
  ZmbM_HermitSkinny_Beige: 'Ermitaño',
  ZmbF_CitizenANormal_Blue: 'Ciudadana',
  ZmbM_CitizenASkinny_Grey: 'Ciudadano',
  ZmbM_PatrolNormal_Autumn: 'Patrullero',
  ZmbF_VillagerOld_Green: 'Aldeana',
  ZmbM_Jacket_brown: 'Hombre con chaqueta',
  ZmbF_JoggerSkinny_Red: 'Corredora',
  ZmbM_HunterOld_Autumn: 'Cazador',
  ZmbM_MotobikerFat_Black: 'Motorista',
  Animal_CervusElaphus: 'Ciervo',
  Animal_CapreolusCapreolus: 'Corzo',
  Animal_GallusGallusDomesticus: 'Gallina',
  Animal_SusScrofa: 'Jabalí',
  Animal_BosTaurus_Brown: 'Vaca',
  SurvivorM_Mirek: 'Mirek',
  SurvivorM_Boris: 'Boris',
  SurvivorM_Denis: 'Denis',
  SurvivorM_Guo: 'Guo',
  SurvivorF_Linda: 'Linda',
  SurvivorF_Maria: 'Maria',
  SurvivorF_Eva: 'Eva',
  SurvivorF_Naomi: 'Naomi',
};

export function objTipo(cls?: string): string {
  if (!cls) return 'generico';
  const t = OBJ_CLASS_TO_TIPO[cls];
  return t && OBJ_PATHS[t] ? t : 'generico';
}

export function KindGlyph({
  kind,
  cls,
}: {
  kind: EntityKind | 'camara' | 'ambiente';
  cls?: string;
}) {
  switch (kind) {
    case 'objeto': {
      const d = cls ? OBJ_PATHS[objTipo(cls)] : 'M3 3h10v10H3z';
      return cls ? (
        <svg className="g" width="14" height="14" viewBox="-8 -8 16 16" aria-hidden="true">
          <path d={d} fill="var(--g-obj)" fillRule="evenodd" />
        </svg>
      ) : (
        <svg className="g" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <rect x="3" y="3" width="10" height="10" rx="1.5" fill="var(--g-obj)" />
        </svg>
      );
    }
    case 'infectado':
      return (
        <svg className="g" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M8 2.5 14 13H2z" fill="var(--g-zmb)" />
        </svg>
      );
    case 'animal':
      return (
        <svg className="g" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M8 1.8 14.2 8 8 14.2 1.8 8z" fill="var(--g-ani)" />
        </svg>
      );
    case 'actor':
      return (
        <svg className="g" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="5.6" fill="var(--g-act)" stroke="var(--line-strong)" />
        </svg>
      );
    case 'camara':
      return (
        <svg className="g" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <rect x="1.5" y="4.5" width="9" height="7" rx="1.5" fill="var(--cam)" />
          <path d="m10.5 7.2 4-2.2v6l-4-2.2z" fill="var(--cam)" />
        </svg>
      );
    case 'ambiente':
      return (
        <svg className="g" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="3.2" fill="var(--accent)" />
          <path
            d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"
            stroke="var(--accent)"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </svg>
      );
  }
}

export function StatusStateIcon({ state }: { state: string }) {
  switch (state) {
    case 'observado':
      return (
        <svg className="sm" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="6.6" fill="currentColor" />
          <path
            d="M5 8.3 7.1 10.3 11 6.1"
            stroke="var(--surface)"
            strokeWidth="1.8"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'aplicado':
      return (
        <svg className="sm" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <circle cx="8" cy="8" r="2.4" fill="currentColor" />
        </svg>
      );
    case 'pendiente':
      return (
        <svg className="sm" viewBox="0 0 16 16" aria-hidden="true">
          <circle
            cx="8"
            cy="8"
            r="6"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeDasharray="2.6 2.4"
          />
        </svg>
      );
    case 'ejecutando':
      return (
        <svg className="sm" viewBox="0 0 16 16" aria-hidden="true">
          <circle
            cx="8"
            cy="8"
            r="6"
            fill="none"
            stroke="currentColor"
            strokeOpacity=".3"
            strokeWidth="1.6"
          />
          <path
            className="spin"
            d="M8 2a6 6 0 0 1 6 6"
            stroke="currentColor"
            strokeWidth="1.9"
            fill="none"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'fallido':
      return (
        <svg className="sm" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M5.3 1.5h5.4l3.8 3.8v5.4l-3.8 3.8H5.3l-3.8-3.8V5.3z"
            fill="currentColor"
          />
          <path
            d="M6.1 6.1l3.8 3.8M9.9 6.1l-3.8 3.8"
            stroke="var(--surface)"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'parcial':
      return (
        <svg className="sm" viewBox="0 0 16 16" aria-hidden="true">
          <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" />
        </svg>
      );
    default:
      return null;
  }
}
