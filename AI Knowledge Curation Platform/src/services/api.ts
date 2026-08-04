import type { DashboardStats, ActivityEvent, Topic, Source, Candidate, Job, Note, VaultNode, VaultFile, Settings } from "../types";
import {
  seedStats, seedActivity, seedTopics, seedSources, seedCandidates,
  seedJobs, seedNotes, seedVaultTree, seedVaultFile, seedSettings,
} from "../data/seed";
import { supabase } from "@/lib/supabase";

export const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export class UnauthorizedError extends Error {
  constructor() { super("Session expired — please sign in again"); }
}

let _isDemo = false;
let _failStreak = 0;
export const isDemoMode = () => _isDemo;

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function GET<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: await getAuthHeaders(),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) throw new Error(`${res.status}`);
    _failStreak = 0;
    _isDemo = false;
    return res.json() as Promise<T>;
  } catch {
    if (++_failStreak >= 2) _isDemo = true;
    return fallback;
  }
}

async function POST<T = void>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...await getAuthHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15000),
  });
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}${text ? ": " + text.slice(0, 120) : ""}`);
  }
  _isDemo = false;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

async function PATCH<T = void>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...await getAuthHeaders() },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}${text ? ": " + text.slice(0, 120) : ""}`);
  }
  _isDemo = false;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

async function DELETE_REQ(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: await getAuthHeaders(),
    signal: AbortSignal.timeout(15000),
  });
  if (res.status === 401) throw new UnauthorizedError();
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}${text ? ": " + text.slice(0, 120) : ""}`);
  }
  _isDemo = false;
}

export const api = {
  dashboard: {
    getStats: () => GET<DashboardStats>("/api/dashboard/stats", seedStats),
    getActivity: () => GET<ActivityEvent[]>("/api/dashboard/activity", seedActivity),
  },
  topics: {
    list: () => GET<Topic[]>("/api/topics", seedTopics),
    create: (label: string) => POST<Topic>("/api/topics", { label }),
    delete: (id: string) => DELETE_REQ(`/api/topics/${id}`),
  },
  sources: {
    list: () => GET<Source[]>("/api/sources", seedSources),
    add: (payload: Partial<Source>) => POST<Source>("/api/sources", payload),
    delete: (id: string) => DELETE_REQ(`/api/sources/${id}`),
  },
  candidates: {
    list: () => GET<Candidate[]>("/api/candidates", seedCandidates),
    approve: async (ids: string[]) => {
      const res = await POST<{ approved: string[]; affected: number }>("/api/candidates/approve", { ids });
      if (ids.length > 0 && res.affected === 0) throw new Error("No records updated — IDs may not exist in the database");
      return res;
    },
    reject: async (ids: string[]) => {
      const res = await POST<{ rejected: string[]; affected: number }>("/api/candidates/reject", { ids });
      if (ids.length > 0 && res.affected === 0) throw new Error("No records updated — IDs may not exist in the database");
      return res;
    },
  },
  jobs: {
    list: () => GET<Job[]>("/api/jobs", seedJobs),
    retry: (id: string) => POST(`/api/jobs/${id}/retry`),
  },
  notes: {
    list: () => GET<Note[]>("/api/notes", seedNotes),
    approve: (id: string) => POST(`/api/notes/${id}/approve`),
    reject: (id: string) => POST(`/api/notes/${id}/reject`),
  },
  vault: {
    tree: () => GET<VaultNode[]>("/api/vault/tree", seedVaultTree),
    file: (path: string) => GET<VaultFile>(`/api/vault/file?path=${encodeURIComponent(path)}`, seedVaultFile),
  },
  settings: {
    get: () => GET<Settings>("/api/settings", seedSettings),
    update: (section: string, payload: unknown) => PATCH(`/api/settings/${section}`, payload),
  },
  scheduler: {
    trigger: () => POST("/api/scheduler/trigger"),
  },
};
