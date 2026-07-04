import type { AgentSummary, ChatRequest, ChatResponse, ConfigResponse, HealthResponse } from "../types";

const BASE = import.meta.env.VITE_BACKEND_URL || window.location.origin;

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request to ${path} failed (${res.status})`);
  }
  return res.json();
}

export function getConfig(): Promise<ConfigResponse> {
  return jsonRequest("/config");
}

export function getHealth(): Promise<HealthResponse> {
  return jsonRequest("/api/health");
}

export function getAgents(): Promise<AgentSummary[]> {
  return jsonRequest("/api/agents");
}

export function postChat(request: ChatRequest): Promise<ChatResponse> {
  return jsonRequest("/api/chat", { method: "POST", body: JSON.stringify(request) });
}

export async function postTts(text: string): Promise<Blob> {
  const res = await fetch(`${BASE}/api/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `TTS request failed (${res.status})`);
  }
  return res.blob();
}
