import type {
  AgentFile,
  Brief,
  Paper,
  ProjectDetail,
  ProjectMeta,
  Report,
  RunEvent,
  RunState,
  Settings,
  ProviderPreset,
} from "./types";

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ ok: boolean; version: string; workspace: string; secret_backend: string }>("/api/health"),

  settings: () =>
    request<{ settings: Settings; providers: Record<string, ProviderPreset>; prices: Record<string, [number, number]> }>(
      "/api/settings",
    ),
  saveSettings: (patch: Record<string, unknown>) =>
    request<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),
  testProvider: () => request<{ ok: boolean; detail: string }>("/api/settings/test", { method: "POST" }),
  listModels: (provider: string) =>
    request<{ ok: boolean; detail: string; models: string[] }>(`/api/providers/${provider}/models`),

  projects: () => request<ProjectMeta[]>("/api/projects"),
  project: (slug: string) => request<ProjectDetail>(`/api/projects/${slug}`),
  createProject: (brief: Brief) =>
    request<{ slug: string }>("/api/projects", { method: "POST", body: JSON.stringify({ brief }) }),
  updateBrief: (slug: string, brief: Brief) =>
    request<{ brief: Brief }>(`/api/projects/${slug}/brief`, { method: "PUT", body: JSON.stringify(brief) }),
  deleteProject: (slug: string) => request<{ deleted: string }>(`/api/projects/${slug}`, { method: "DELETE" }),
  duplicateProject: (slug: string) =>
    request<{ slug: string }>(`/api/projects/${slug}/duplicate`, { method: "POST", body: JSON.stringify({}) }),
  importProject: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ slug: string }>("/api/projects/import", { method: "POST", body: form });
  },

  papers: (slug: string) => request<Paper[]>(`/api/projects/${slug}/papers`),
  paper: (slug: string, id: string) =>
    request<{ paper: Paper; evidence: { locator: string; text: string; summary: string }[] }>(
      `/api/projects/${slug}/papers/${id}`,
    ),
  addSource: (slug: string, payload: { doi?: string; title?: string; abstract?: string }) =>
    request<{ id: string; existing: boolean }>(`/api/projects/${slug}/add-source`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  diagnose: (slug: string) =>
    request<import("./types").Diagnosis>(`/api/projects/${slug}/diagnose`, { method: "POST" }),

  runs: (slug: string) => request<RunState[]>(`/api/projects/${slug}/runs`),
  startRun: (slug: string) =>
    request<RunState>(`/api/projects/${slug}/runs`, { method: "POST" }),
  runEvents: (slug: string, runId: string, offset = 0) =>
    request<{ events: RunEvent[]; offset: number; state: RunState | null }>(
      `/api/projects/${slug}/runs/${runId}/events?offset=${offset}`,
    ),
  decide: (slug: string, runId: string, payload: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/projects/${slug}/runs/${runId}/decide`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancelRun: (slug: string, runId: string) =>
    request<{ ok: boolean }>(`/api/projects/${slug}/runs/${runId}/cancel`, { method: "POST" }),
  report: (slug: string, runId: string) => request<Report>(`/api/projects/${slug}/runs/${runId}/report`),
  artifact: async (slug: string, runId: string, name: string) => {
    const response = await fetch(
      `/api/projects/${slug}/runs/${runId}/artifact?name=${encodeURIComponent(name)}`,
    );
    if (!response.ok) throw new Error("artifact not found");
    return response.text();
  },

  agent: (slug: string, id: string) => request<AgentFile>(`/api/projects/${slug}/agents/${id}`),
  saveAgent: (slug: string, id: string, payload: Record<string, unknown>) =>
    request<AgentFile>(`/api/projects/${slug}/agents/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  resetAgent: (slug: string, id: string) =>
    request<AgentFile>(`/api/projects/${slug}/agents/${id}/reset`, { method: "POST" }),
  previewAgent: (slug: string, id: string) =>
    request<{ system: string; user_sample: string; system_tokens: number; user_tokens: number }>(
      `/api/projects/${slug}/agents/${id}/preview`,
    ),
};

export function download(url: string) {
  const link = document.createElement("a");
  link.href = url;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
