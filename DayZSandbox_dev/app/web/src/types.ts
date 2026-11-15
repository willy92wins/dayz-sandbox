export type ModeName = 'escena' | 'rodaje';

export type EntityKind = 'actor' | 'objeto' | 'infectado' | 'animal';

export interface MarkItem {
  x: number;
  z: number;
}

export interface GestureItem {
  emote: string;
  at?: number;
  t?: number;
}

export interface SceneEntity {
  id: string;
  kind: EntityKind;
  cls: string;
  name: string;
  x: number;
  z: number;
  yaw: number;
  wardrobe?: string;
  behaviour?: string;
  roam?: number;
  marks?: MarkItem[];
  gestures?: GestureItem[];
  [key: string]: unknown;
}

export interface CameraKey {
  t: number;
  x: number;
  y: number;
  z: number;
  yaw: number;
  pitch: number;
  fov: number;
  focus: number;
}

export interface SceneCamera {
  id: string;
  name: string;
  keys: CameraKey[];
}

export interface SceneAmbiente {
  fecha: string;
  hora: string;
  nubes: number;
  niebla: number;
  lluvia: number;
  viento: number;
  [key: string]: unknown;
}

export interface SceneDoc {
  schema: string;
  doc_id: string;
  name: string;
  map: string;
  ambiente: SceneAmbiente;
  entities: SceneEntity[];
  cameras: SceneCamera[];
  next: Record<string, number>;
}

export interface OpData {
  op_id: string;
  state: string;
  rev?: number;
  hash?: string;
  at_ms?: number;
  origin?: string;
  age_ms?: number;
  reason?: string | null;
  verb?: string | null;
}

export interface Anchor {
  atMs: number;
  ageMs: number | null;
  perfMs: number;
  unknown: boolean;
}

export interface QueueRow {
  op_id: string;
  state: string;
  rev?: number;
  hash?: string;
  at_ms?: number;
  origin?: string;
  reason?: string | null;
  verb?: string | null;
  anchor: Anchor;
}

export interface ApplyErrorInfo {
  code: string;
  pointer: string;
  msg: string;
}

export interface CatalogResponse {
  ok: boolean;
  source: string;
  classes: Record<EntityKind, string[]>;
  caps: Record<EntityKind, number>;
  wardrobes: string[];
  emotes: string[];
}

export interface JsonSchemaProperty {
  $ref?: string;
  type?: string;
  const?: string;
  enum?: string[];
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  pattern?: string;
  additionalProperties?: boolean;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  items?: JsonSchemaProperty;
  oneOf?: JsonSchemaProperty[];
}

export interface SceneSchemaDoc {
  $schema?: string;
  $id?: string;
  title?: string;
  type: string;
  required?: string[];
  properties: Record<string, JsonSchemaProperty>;
  $defs: Record<string, JsonSchemaProperty>;
}

export interface ProfilePayload {
  v: 1;
  layouts: {
    escena: Record<string, unknown> | null;
    rodaje: Record<string, unknown> | null;
  };
  keymap: Record<string, string | null>;
}

export interface ValidationErrorItem {
  id: string;
  pointer: string;
  code: string;
  msg: string;
  targetId: string | null; // entity id or 'ambiente' or null
  field: string | null;
}

export interface RejectedDraft {
  targetId: string; // entity id or 'ambiente'
  field: string;
  rawValue: string;
  code: string;
  msg: string;
  pointer: string;
}

export type NoticeKind =
  | 'perfil-corrupto'
  | 'layout-incompatible'
  | 'atajos-corregidos'
  | 'sin-backend'
  | 'deshacer-parcial'
  | 'perfil-no-guardado'
  | 'quitar-no-disponible'
  | 'info';

export interface NoticeItem {
  kind: NoticeKind;
  message: string;
}

export type EscenaPanelId =
  | 'jerarquia'
  | 'mapa'
  | 'propiedades'
  | 'anadir'
  | 'actividad'
  | 'validacion'
  | 'historial'
  | 'ia';

export type RodajePanelId =
  | 'camaras'
  | 'tomas'
  | 'mapa'
  | 'preparacion'
  | 'propiedades'
  | 'actividad'
  | 'vista-previa';

export type StudioPanelId = EscenaPanelId | RodajePanelId;
