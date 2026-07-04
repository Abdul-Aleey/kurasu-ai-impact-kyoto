export type InputMode = "typed" | "voice";

export interface Attachment {
  mimeType: string;
  dataBase64: string;
}

export interface HistoryTurn {
  role: "user" | "model";
  text?: string;
  attachments?: Attachment[];
  inputMode?: InputMode;
  specialistUsed?: string;
}

export interface NewTurn {
  text?: string;
  attachments?: Attachment[];
  inputMode: InputMode;
}

export interface DeviceContext {
  lat?: number;
  lng?: number;
  currentTimeIso?: string;
}

export interface ChatRequest {
  agentId: string;
  history: HistoryTurn[];
  newTurn: NewTurn;
  deviceContext: DeviceContext;
}

export interface GeneratedFile {
  filename: string;
  mimeType: string;
  dataBase64: string;
}

export interface ChatResponse {
  status: "collecting" | "final_answer";
  text: string;
  specialistUsed?: string;
  generatedFiles?: GeneratedFile[];
}

export interface AgentSummary {
  id: string;
  title: string;
  subtitle: string;
  icon: string;
  hasImageInput: boolean;
  usesLocation: boolean;
  welcomeMessage: string;
  maxImages: number;
  longWaitMessage: string;
}

export interface ConfigResponse {
  backendReady: boolean;
  usingVertexAi: boolean;
}

export interface HealthResponse {
  modelConnected: boolean;
  detail: string;
}

/** A turn as displayed in the chat UI -- one bubble. */
export interface Turn {
  role: "user" | "model";
  text: string;
  inputMode?: InputMode;
  attachments?: Attachment[];
  pending?: boolean;
  generatedFiles?: GeneratedFile[];
  specialistUsed?: string;
}
