export interface DashboardStats {
  pendingApprovals: number;
  runningJobs: number;
  queuedJobs: number;
  notesToday: number;
  sourcesIndexed: number;
  pipelineCounts: Record<string, number>;
}

export interface ActivityEvent {
  id: string;
  type: "approved" | "merged" | "created" | "failed" | "synced" | "rejected" | "indexed";
  message: string;
  timestamp: string;
}

export interface Topic {
  id: string;
  label: string;
  color: string;
}

export interface Source {
  id: string;
  type: "youtube" | "web" | "pdf" | "local";
  title: string;
  url: string;
  topicId: string | null;
  status: "queued" | "processing" | "done" | "failed";
  addedAt: string;
  schedule: string | null;
}

export interface Candidate {
  id: string;
  title: string;
  sourceInfo: string;
  domain: string;
  publishedAt: string;
  topicId: string | null;
  recommendation: "process" | "merge" | "skip" | "review";
  qualityScore: number;
  confidenceScore: number;
  duplicateScore: number;
  expectedNotes: number;
  estimatedTokens: number;
  summary: string;
  extractedTopics: string[];
  status: "pending" | "approved" | "rejected";
}

export interface Job {
  id: string;
  sourceTitle: string;
  type: "Extraction" | "Transcription" | "Analysis" | "PII Check" | "Note Gen" | "Verification" | "Graphify Sync" | "Cleanup";
  status: "running" | "queued" | "completed" | "failed";
  progress: number;
  startedAt: string;
  duration: string;
  error?: string;
  artifactPath?: string;
}

export interface Note {
  id: string;
  title: string;
  source: string;
  generatedAt: string;
  aiAction: "created" | "merged" | "updated" | "skipped";
  qualityScore: number;
  hasDuplicate: boolean;
  content: string;
  frontmatter: Record<string, string>;
  citations: string[];
  wikiLinks: string[];
  similarityReasoning: string;
  similarTo?: string;
}

export interface VaultNode {
  name: string;
  path: string;
  type: "file" | "folder";
  children?: VaultNode[];
}

export interface VaultFile {
  path: string;
  content: string;
  frontmatter: Record<string, string>;
  lastModified: string;
  wordCount: number;
  backlinks: number;
  graphNodeType: string;
  cloudSafe: boolean;
}

export interface AIProvidersRead {
  claudeKeySet: boolean;
  openaiKeySet: boolean;
  ollamaUrl: string;
  fallbackOrder: string[];
}

export interface AIProvidersWrite {
  claudeKey?: string;
  openaiKey?: string;
  ollamaUrl: string;
  fallbackOrder: string[];
}

export interface Settings {
  vault: { path: string; name: string };
  aiProviders: AIProvidersRead;
  privacy: { piiMode: "regex" | "ml"; blockInsuranceData: boolean; cloudBlockList: string[] };
  discovery: { defaultInterval: number; youtubeInterval: number; webInterval: number; pdfInterval: number; localDebounce: number };
  cleanup: { youtube: "keep" | "zip" | "delete"; web: "keep" | "zip" | "delete"; pdf: "keep" | "zip" | "delete"; local: "keep" | "zip" | "delete" };
  notifications: { desktop: boolean; inApp: boolean; email: boolean; emailProvider: "resend" | "sendgrid" | "smtp"; emailAddress: string };
  team: { tier: "single" | "small" | "larger"; members: { id: string; name: string; email: string; role: "admin" | "editor" | "viewer" }[] };
}

export interface FailedJob {
  id: string;
  sourceTitle: string;
  error: string;
}
