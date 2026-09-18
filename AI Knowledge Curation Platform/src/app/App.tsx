import DOMPurify from "dompurify";
import { useState, useEffect, useRef } from "react";
import { toast, Toaster } from "sonner";
import { useAuth } from "../hooks/useAuth";
import { LoginPage } from "./LoginPage";
import {
  LayoutDashboard, Globe, CheckSquare, Cpu, BookOpen, FolderOpen, Settings,
  RefreshCw, Play, ChevronDown, ChevronRight, Tag, Shield, AlertTriangle,
  CheckCircle2, XCircle, Clock, FileText, Link2, Zap, Plus, Trash2, Eye, EyeOff,
  Youtube, File, FolderClosed, Search, ArrowRight, X,
  GitMerge, SkipForward, Wifi, WifiOff, RotateCcw, Activity,
} from "lucide-react";
import { useApi } from "../hooks/useApi";
import { api, isDemoMode, BASE } from "../services/api";
import { sourceScopeLabel } from "./sourceScopeLabel";
import type { Topic, Source, Candidate, Job, Note, VaultNode, VaultFile } from "../types";
import {
  seedTopics, seedSources, seedVaultTree, seedSettings,
} from "../data/seed";

// ─── Design primitives ────────────────────────────────────────────────────────

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-100 ${className}`} />;
}

type BadgeVariant = "default" | "success" | "warning" | "danger" | "info" | "neutral" | "amber" | "teal";

function Badge({ children, variant = "default" }: { children: React.ReactNode; variant?: BadgeVariant }) {
  const styles: Record<BadgeVariant, string> = {
    default:  "bg-slate-100 text-slate-600",
    success:  "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    warning:  "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    danger:   "bg-red-50 text-red-700 ring-1 ring-red-200",
    info:     "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
    neutral:  "bg-slate-100 text-slate-500",
    amber:    "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    teal:     "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${styles[variant]}`}>
      {children}
    </span>
  );
}

function Button({
  children, onClick, variant = "primary", size = "md", disabled = false, className = "",
}: {
  children: React.ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost" | "danger" | "success";
  size?: "sm" | "md"; disabled?: boolean; className?: string;
}) {
  const base = "inline-flex items-center gap-1.5 font-medium rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed";
  const sizes = { sm: "px-3 py-1.5 text-xs", md: "px-4 py-2 text-sm" };
  const variants = {
    primary:   "bg-blue-600 text-white hover:bg-blue-700 shadow-sm",
    secondary: "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 shadow-sm",
    ghost:     "text-slate-600 hover:bg-slate-100 hover:text-slate-800",
    danger:    "bg-red-50 text-red-700 border border-red-200 hover:bg-red-100",
    success:   "bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100",
  };
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

function SectionHeader({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {description && <p className="text-sm text-slate-500 mt-0.5">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

function EmptyState({ icon, title, description }: { icon: React.ReactNode; title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="size-12 rounded-full bg-slate-100 flex items-center justify-center mb-3 text-slate-400">{icon}</div>
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {description && <p className="text-xs text-slate-400 mt-1">{description}</p>}
    </div>
  );
}

// ─── Status and type helpers ──────────────────────────────────────────────────

function sourceTypeIcon(type: Source["type"]) {
  const cls = "size-4";
  if (type === "youtube") return <Youtube className={cls} />;
  if (type === "pdf") return <File className={cls} />;
  if (type === "local") return <FolderClosed className={cls} />;
  return <Globe className={cls} />;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "done" || status === "completed") return <Badge variant="success"><CheckCircle2 className="size-3" />Completed</Badge>;
  if (status === "running" || status === "processing") return <Badge variant="teal"><Activity className="size-3" />Running</Badge>;
  if (status === "queued") return <Badge variant="neutral"><Clock className="size-3" />Queued</Badge>;
  if (status === "failed") return <Badge variant="danger"><XCircle className="size-3" />Failed</Badge>;
  if (status === "approved") return <Badge variant="success"><CheckCircle2 className="size-3" />Approved</Badge>;
  if (status === "rejected") return <Badge variant="danger"><XCircle className="size-3" />Rejected</Badge>;
  if (status === "pending") return <Badge variant="warning"><Clock className="size-3" />Pending</Badge>;
  return <Badge>{status}</Badge>;
}

function RecommendationBadge({ rec }: { rec: Candidate["recommendation"] }) {
  if (rec === "process") return <Badge variant="info">Process</Badge>;
  if (rec === "merge") return <Badge variant="amber">Merge</Badge>;
  if (rec === "skip") return <Badge variant="neutral">Skip</Badge>;
  return <Badge variant="warning">Review</Badge>;
}

function AiActionBadge({ action }: { action: Note["aiAction"] }) {
  if (action === "created") return <Badge variant="info">Created</Badge>;
  if (action === "merged") return <Badge variant="amber">Merged</Badge>;
  if (action === "updated") return <Badge variant="teal">Updated</Badge>;
  return <Badge variant="neutral">Skipped</Badge>;
}

function renderMarkdown(md: string): string {
  return md
    .replace(/```(\w+)?\n([\s\S]+?)```/g, '<pre class="bg-slate-50 border border-slate-200 rounded-lg p-4 my-3 overflow-x-auto font-mono text-xs text-slate-700 whitespace-pre">$2</pre>')
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold text-slate-800 mt-4 mb-1.5">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-semibold text-slate-900 mt-5 mb-2">$1</h2>')
    .replace(/^- (.+)$/gm, '<li class="ml-5 list-disc text-slate-600 text-sm mb-1">$1</li>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-slate-800 font-semibold">$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="font-mono text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">$1</code>')
    .replace(/\[\[(.+?)\]\]/g, '<span class="text-blue-600 font-mono text-xs bg-blue-50 px-1 py-0.5 rounded">[[<span>$1</span>]]</span>')
    .replace(/\n\n/g, '</p><p class="mb-3 text-slate-600 text-sm leading-relaxed">')
    .replace(/^(?!<[hlpli])(.+)$/gm, '<p class="mb-3 text-slate-600 text-sm leading-relaxed">$1</p>');
}

function relativeTime(ts: string): string {
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (isNaN(diff) || diff < 0) return ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function timeAgo(iso: string): string {
  return relativeTime(iso);
}

function timeUntil(iso: string): string {
  const diff = Math.floor((new Date(iso).getTime() - Date.now()) / 1000);
  if (isNaN(diff) || diff <= 0) return "now";
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function formatDateTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return ts;
  }
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function DashboardScreen({ onNavigateToSources }: { onNavigateToSources: () => void }) {
  const { data: stats, loading: statsLoading, refetch: refetchStats } = useApi(api.dashboard.getStats);
  const { data: activity, loading: actLoading } = useApi(api.dashboard.getActivity);
  const { data: candidates } = useApi(api.candidates.list);
  const { data: jobs } = useApi(api.jobs.list);
  const { data: sources } = useApi(api.sources.list);
  const hasNoSources = sources !== null && sources.length === 0;

  const pipeline = ["discover", "analyze", "approve", "extract", "transcribe", "generate", "verify", "graphify", "cleanup"];
  const pipelineLabels: Record<string, string> = { discover: "Discover", analyze: "Analyze", approve: "Approve", extract: "Extract", transcribe: "Transcribe", generate: "Generate", verify: "Verify", graphify: "Graphify", cleanup: "Cleanup" };
  const failedJobs = (jobs ?? []).filter((j) => j.status === "failed");
  const pending = (candidates ?? []).filter((c) => c.status === "pending").slice(0, 3);

  const [, setNowTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setNowTick((t) => t + 1), 60000);
    return () => clearInterval(id);
  }, []);

  const [syncStatus, setSyncStatus] = useState<{ last_run_at: string | null; next_run_at: string | null; is_running: boolean }>({ last_run_at: null, next_run_at: null, is_running: false });
  useEffect(() => {
    const poll = () => {
      if (document.visibilityState === "visible") {
        api.scheduler.status().then(setSyncStatus);
      }
    };

    poll();
    const jitter = Math.random() * 10000;
    const id = setInterval(poll, 30000 + jitter);
    const onVisibility = () => { if (document.visibilityState === "visible") poll(); };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const [triggering, setTriggering] = useState(false);
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());
  async function handleTrigger() {
    if (triggering) return;
    if (hasNoSources) {
      onNavigateToSources();
      return;
    }
    setTriggering(true);
    try { await api.scheduler.trigger(); toast.success("Discovery run triggered"); refetchStats(); }
    catch (e) { toast.error(`Failed to trigger run: ${e instanceof Error ? e.message : "Request failed"}`); }
    finally { setTriggering(false); }
  }

  const kpis = [
    { label: "Pending Approvals", value: stats?.pendingApprovals ?? 0, sub: "Waiting for your review", icon: <CheckSquare className="size-5 text-amber-500" />, bg: "bg-amber-50" },
    { label: "Active Jobs", value: (stats?.runningJobs ?? 0) + (stats?.queuedJobs ?? 0), sub: `${stats?.runningJobs ?? 0} running · ${stats?.queuedJobs ?? 0} queued`, icon: <Cpu className="size-5 text-teal-500" />, bg: "bg-teal-50" },
    { label: "Notes Published Today", value: stats?.notesToday ?? 0, sub: "Added to your vault", icon: <FileText className="size-5 text-blue-500" />, bg: "bg-blue-50" },
    { label: "Sources Indexed", value: stats?.sourcesIndexed ?? 0, sub: "Tracked sources", icon: <Globe className="size-5 text-slate-500" />, bg: "bg-slate-100" },
  ];

  const actIcons: Record<string, React.ReactNode> = {
    approved: <div className="size-6 rounded-full bg-emerald-100 flex items-center justify-center shrink-0"><CheckCircle2 className="size-3.5 text-emerald-600" /></div>,
    merged:   <div className="size-6 rounded-full bg-amber-100 flex items-center justify-center shrink-0"><GitMerge className="size-3.5 text-amber-600" /></div>,
    created:  <div className="size-6 rounded-full bg-blue-100 flex items-center justify-center shrink-0"><FileText className="size-3.5 text-blue-600" /></div>,
    failed:   <div className="size-6 rounded-full bg-red-100 flex items-center justify-center shrink-0"><XCircle className="size-3.5 text-red-600" /></div>,
    synced:   <div className="size-6 rounded-full bg-teal-100 flex items-center justify-center shrink-0"><Zap className="size-3.5 text-teal-600" /></div>,
    indexed:  <div className="size-6 rounded-full bg-slate-100 flex items-center justify-center shrink-0"><FolderOpen className="size-3.5 text-slate-500" /></div>,
    rejected: <div className="size-6 rounded-full bg-slate-100 flex items-center justify-center shrink-0"><SkipForward className="size-3.5 text-slate-400" /></div>,
  };

  return (
    <div className="p-6 max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Good morning 👋</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {hasNoSources
              ? "No sources yet — add one to get started"
              : syncStatus.is_running
                ? "Discovery running now..."
                : syncStatus.last_run_at
                  ? `Last sync ran ${timeAgo(syncStatus.last_run_at)}${syncStatus.next_run_at ? ` · Next in ${timeUntil(syncStatus.next_run_at)}` : ""}`
                  : "No sync runs yet"}
          </p>
        </div>
        <Button onClick={handleTrigger} variant="primary" disabled={triggering}>
          <Play className="size-4" />{triggering ? "Running…" : hasNoSources ? "Add a Source" : "Run Discovery Now"}
        </Button>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k) => (
          <Card key={k.label} className="p-5">
            {statsLoading ? (
              <><Skeleton className="h-4 w-24 mb-4" /><Skeleton className="h-8 w-12" /></>
            ) : (
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-slate-500 leading-tight">{k.label}</p>
                  <p className="text-3xl font-bold text-slate-900 mt-1">{k.value}</p>
                  <p className="text-xs text-slate-400 mt-1">{k.sub}</p>
                </div>
                <div className={`size-10 rounded-xl ${k.bg} flex items-center justify-center shrink-0`}>{k.icon}</div>
              </div>
            )}
          </Card>
        ))}
      </div>

      {/* Pipeline */}
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">Knowledge Pipeline</h2>
        <div className="flex items-center overflow-x-auto pb-2">
          {pipeline.map((stage, i) => {
            const count = stats?.pipelineCounts?.[stage] ?? 0;
            return (
              <div key={stage} className="flex items-center shrink-0">
                <div className={`flex flex-col items-center px-3 py-2.5 rounded-xl min-w-[76px] transition-colors ${count > 0 ? "bg-blue-50 ring-1 ring-blue-200" : "bg-slate-50"}`}>
                  <span className={`text-xl font-bold ${count > 0 ? "text-blue-600" : "text-slate-300"}`}>{count}</span>
                  <span className="text-xs text-slate-500 mt-0.5 whitespace-nowrap">{pipelineLabels[stage]}</span>
                </div>
                {i < pipeline.length - 1 && <ArrowRight className="size-3.5 text-slate-300 shrink-0 mx-1.5" />}
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Activity */}
        <Card className="p-5">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">Recent Activity</h2>
          <div className="space-y-3">
            {actLoading
              ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)
              : (activity ?? []).map((ev) => (
                <div key={ev.id} className="flex items-start gap-3">
                  {actIcons[ev.type] ?? <div className="size-6 rounded-full bg-slate-100 flex items-center justify-center shrink-0"><Clock className="size-3.5 text-slate-400" /></div>}
                  <div className="min-w-0 pt-0.5">
                    <p className="text-sm text-slate-700 leading-snug">{ev.message}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{relativeTime(ev.timestamp)}</p>
                  </div>
                </div>
              ))}
          </div>
        </Card>

        {/* Pending quick actions */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-700">Needs Your Approval</h2>
            <Badge variant="warning">{stats?.pendingApprovals ?? 0} pending</Badge>
          </div>
          <div className="space-y-3">
            {pending.length === 0
              ? <EmptyState icon={<CheckSquare className="size-5" />} title="All caught up!" description="No candidates waiting for review" />
              : pending.map((c) => (
                <div key={c.id} className="flex items-start gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-800 font-medium leading-snug line-clamp-1">{c.title}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{c.domain}</p>
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button className="text-xs px-2.5 py-1 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors font-medium">Approve</button>
                    <button className="text-xs px-2.5 py-1 rounded-lg bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 transition-colors font-medium">Skip</button>
                  </div>
                </div>
              ))}
          </div>
        </Card>
      </div>

      {/* Failures */}
      {failedJobs.length > 0 && (
        <Card className="p-5 border-red-200 bg-red-50/30">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="size-4 text-red-500" />
            <h2 className="text-sm font-semibold text-slate-800">{failedJobs.length} job{failedJobs.length !== 1 ? "s" : ""} need{failedJobs.length === 1 ? "s" : ""} attention</h2>
          </div>
          <div className="space-y-2.5">
            {failedJobs.map((j) => (
              <div key={j.id} className="flex items-start justify-between gap-4 p-3 bg-white rounded-xl border border-red-100">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{j.sourceTitle}</p>
                  <p className="text-xs font-mono text-slate-400 mt-0.5">{j.id}</p>
                  {j.error && <p className="text-xs text-red-600 mt-1 line-clamp-1">{j.error}</p>}
                </div>
                {/cuda out of memory|oom|out of memory/i.test(j.error ?? "") ? (
                  <span className="text-xs text-amber-600 font-medium">Adjust model / device</span>
                ) : (
                  <Button size="sm" variant="secondary" disabled={retryingIds.has(j.id)} onClick={async () => {
                    setRetryingIds((s) => { const n = new Set(s); n.add(j.id); return n; });
                    try { await api.jobs.retry(j.id); toast.success("Retrying…"); refetchStats(); }
                    catch (e) { toast.error(`Retry failed: ${e instanceof Error ? e.message : "Request failed"}`); }
                    finally { setRetryingIds((s) => { const n = new Set(s); n.delete(j.id); return n; }); }
                  }}>
                    <RotateCcw className="size-3" /> {retryingIds.has(j.id) ? "Retrying…" : "Retry"}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

// ─── Sources ──────────────────────────────────────────────────────────────────

function SourcesScreen() {
  const { data: sources, loading, refetch } = useApi(api.sources.list, seedSources);
  const { data: topics, refetch: refetchTopics } = useApi(api.topics.list, seedTopics);
  const [filter, setFilter] = useState<"all" | Source["type"]>("all");
  const [showModal, setShowModal] = useState(false);
  const [newTopicLabel, setNewTopicLabel] = useState("");

  // YouTube Track B state
  const [youtubeMode, setYoutubeMode] = useState<"find" | "monitor">("find");
  const [youtubeQuery, setYoutubeQuery] = useState("");
  const [youtubeLimit, setYoutubeLimit] = useState(10);
  const [youtubeSearchResults, setYoutubeSearchResults] = useState<YouTubeSearchItem[]>([]);
  const [youtubeSelected, setYoutubeSelected] = useState<Set<string>>(new Set());
  const [youtubeSearching, setYoutubeSearching] = useState(false);
  const [youtubeBatchProcessing, setYoutubeBatchProcessing] = useState<Map<string, string>>(new Map());
  const youtubeSearchAbortRef = useRef<AbortController | null>(null);

  // YouTube Track A state
  const [youtubeTrackAMode, setYoutubeTrackAMode] = useState<"channel" | "keyword">("channel");
  const [youtubeTrackAUrl, setYoutubeTrackAUrl] = useState("");
  const [youtubeTrackAKeyword, setYoutubeTrackAKeyword] = useState("");
  const [youtubeTrackALimit, setYoutubeTrackALimit] = useState(25);
  const [youtubeTrackATopic, setYoutubeTrackATopic] = useState("");
  const [youtubeTrackASaving, setYoutubeTrackASaving] = useState(false);

  // Website state
  const [websiteKeyword, setWebsiteKeyword] = useState("");
  const [websiteLimit, setWebsiteLimit] = useState(5);
  const [websiteTopic, setWebsiteTopic] = useState("");
  const [websiteSaving, setWebsiteSaving] = useState(false);

  // AI parse state
  const [youtubeParseMessage, setYoutubeParseMessage] = useState("");
  const [youtubeParsePending, setYoutubeParsePending] = useState(false);
  const [youtubeParsedConfidence, setYoutubeParsedConfidence] = useState<number | null>(null);

  const filtered = (sources ?? []).filter((s) => filter === "all" || s.type === filter);
  const tabs: { key: "all" | Source["type"]; label: string }[] = [
    { key: "all", label: "All" }, { key: "youtube", label: "YouTube" },
    { key: "web", label: "Web" }, { key: "pdf", label: "PDF" }, { key: "local", label: "Local Folder" },
  ];

  async function handleYoutubeSearch() {
    if (!youtubeQuery.trim() || youtubeSearching) return;
    youtubeSearchAbortRef.current = new AbortController();
    setYoutubeSearching(true);
    setYoutubeSelected(new Set());
    try {
      const response = await api.youtube.search(youtubeQuery.trim(), youtubeLimit);
      setYoutubeSearchResults(response.results || []);
      if (response.error) toast.error(`Search failed: ${response.error}`);
    } catch (e) {
      toast.error(`Search error: ${e instanceof Error ? e.message : "Request failed"}`);
    } finally {
      setYoutubeSearching(false);
    }
  }

  async function handleYoutubeParseIntent() {
    if (!youtubeParseMessage.trim() || youtubeParsePending) return;
    setYoutubeParsePending(true);
    try {
      const response = await api.youtube.parseIntent(youtubeParseMessage.trim());
      setYoutubeQuery(response.search_query);
      setYoutubeLimit(response.limit);
      setYoutubeParsedConfidence(response.confidence);
      if (response.confidence < 0.6) {
        toast.warning("Low confidence — please review the parsed query");
      }
      setYoutubeSearchResults([]);
      setYoutubeSelected(new Set());
    } catch (e) {
      toast.error(`Parse failed: ${e instanceof Error ? e.message : "Request failed"}`);
    } finally {
      setYoutubeParsePending(false);
    }
  }

  async function handleCreateNotesFromSelected() {
    if (youtubeSelected.size === 0 || youtubeBatchProcessing.size > 0) return;
    const urls = Array.from(youtubeSelected).map((videoId) => {
      const result = youtubeSearchResults.find((r) => r.video_id === videoId);
      return result?.url || "";
    }).filter(Boolean as any);

    const processing = new Map<string, string>();
    urls.forEach((url) => processing.set(url, "PROCESSING"));
    setYoutubeBatchProcessing(processing);

    try {
      const response = await api.youtube.createNotesBatch(urls);
      for (const item of response.results) {
        processing.set(item.url, item.status);
      }
      setYoutubeBatchProcessing(new Map(processing));
      toast.success(`Batch processing complete: ${response.results.filter((r) => r.status === "SUCCESS").length} created`);
    } catch (e) {
      toast.error(`Batch failed: ${e instanceof Error ? e.message : "Request failed"}`);
    }
  }

  async function handleYoutubeTrackASave() {
    const url = youtubeTrackAMode === "channel" ? youtubeTrackAUrl.trim() : "";
    const keyword = youtubeTrackAMode === "keyword" ? youtubeTrackAKeyword.trim() : "";
    if (!url && !keyword) return;
    if (youtubeTrackASaving) return;

    setYoutubeTrackASaving(true);
    try {
      await api.sources.add({
        url: url,
        type: "youtube",
        topicId: youtubeTrackATopic || null,
        discovery_mode: youtubeTrackAMode === "channel" ? "channel_playlist" : "keyword",
        keyword: keyword,
        discovery_limit: youtubeTrackALimit,
      });
      toast.success("YouTube source saved");
      setYoutubeTrackAUrl("");
      setYoutubeTrackAKeyword("");
      setYoutubeTrackATopic("");
      setYoutubeTrackALimit(25);
      refetch();
    } catch (e) {
      toast.error(`Failed to save: ${e instanceof Error ? e.message : "Request failed"}`);
    } finally {
      setYoutubeTrackASaving(false);
    }
  }

  async function handleWebsiteSave() {
    if (!websiteKeyword.trim() || websiteSaving) return;
    setWebsiteSaving(true);
    try {
      await api.sources.add({
        url: "",
        type: "web",
        topicId: websiteTopic || null,
        discovery_mode: "web_keyword",
        keyword: websiteKeyword.trim(),
        discovery_limit: websiteLimit,
      });
      toast.success("Website source saved");
      setWebsiteKeyword("");
      setWebsiteTopic("");
      setWebsiteLimit(5);
      refetch();
    } catch (e) {
      toast.error(`Failed to save: ${e instanceof Error ? e.message : "Request failed"}`);
    } finally {
      setWebsiteSaving(false);
    }
  }

  async function handleAddTopic() {
    if (!newTopicLabel.trim()) return;
    try {
      await api.topics.create(newTopicLabel.trim());
      toast.success(`Topic "${newTopicLabel.trim()}" created`);
      setNewTopicLabel(""); refetchTopics();
    } catch { toast.error("Failed to create topic"); }
  }

  function toggleYoutubeSelect(videoId: string) {
    const updated = new Set(youtubeSelected);
    if (updated.has(videoId)) {
      updated.delete(videoId);
    } else {
      updated.add(videoId);
    }
    setYoutubeSelected(updated);
  }

  const typeColors: Record<string, string> = { youtube: "text-red-500", pdf: "text-orange-500", local: "text-amber-600", web: "text-slate-500" };
  const typeBg: Record<string, string> = { youtube: "bg-red-50", pdf: "bg-orange-50", local: "bg-amber-50", web: "bg-slate-100" };

  return (
    <div className="p-6 max-w-6xl space-y-5">
      <SectionHeader
        title="Sources"
        description="Manage where Synker discovers and ingests knowledge from"
        action={<Button onClick={() => setShowModal(true)} variant="primary"><Plus className="size-4" />Add Source</Button>}
      />

      {/* Discovery Topics */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <Tag className="size-4 text-blue-500" />
          <h2 className="text-sm font-semibold text-slate-800">Discovery Topics</h2>
          <span className="text-xs text-slate-400">AI classifies sources into these categories</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {(topics ?? []).map((t) => (
            <span key={t.id} className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border" style={{ borderColor: t.color + "60", color: t.color, background: t.color + "18" }}>
              {t.label}
              <button onClick={async () => { try { await api.topics.delete(t.id); refetchTopics(); } catch { toast.error("Failed to delete topic"); } }} className="opacity-50 hover:opacity-100 transition-opacity ml-0.5">
                <X className="size-2.5" />
              </button>
            </span>
          ))}
          <div className="flex items-center gap-1.5">
            <input
              value={newTopicLabel}
              onChange={(e) => setNewTopicLabel(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAddTopic()}
              placeholder="Add a topic…"
              className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 w-32 transition-all"
            />
            <button onClick={handleAddTopic} className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors text-slate-500">
              <Plus className="size-3.5" />
            </button>
          </div>
        </div>
      </Card>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setFilter(t.key)}
            className={`px-4 py-1.5 text-xs font-medium rounded-lg transition-all ${filter === t.key ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="p-8">
          <EmptyState icon={<Globe className="size-6" />} title="No sources yet" description="Add a URL, PDF, or local folder to get started" />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((s) => {
            const topic = (topics ?? []).find((t) => t.id === s.topicId);
            return (
              <Card key={s.id} className="p-4 flex flex-col gap-3 group hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-2">
                  <div className={`size-8 rounded-lg ${typeBg[s.type]} flex items-center justify-center shrink-0`}>
                    <span className={typeColors[s.type]}>{sourceTypeIcon(s.type)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={s.status} />
                    {(s.status === "done" || s.status === "processing" || s.status === "failed") && (
                      <button
                        onClick={() => api.sources.reset(s.id).then(() => { toast.success("Source reset to queued"); refetch(); }).catch((e: unknown) => toast.error(`Reset failed: ${e instanceof Error ? e.message : "Request failed"}`))}
                        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg hover:bg-blue-50 text-slate-400 hover:text-blue-500"
                        title="Reset to queued"
                      >
                        <RotateCcw className="size-3.5" />
                      </button>
                    )}
                    <button onClick={() => api.sources.delete(s.id).then(() => { toast.success("Removed"); refetch(); }).catch((e: unknown) => toast.error(`Remove failed: ${e instanceof Error ? e.message : "Request failed"}`))}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500">
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-slate-800 line-clamp-2 leading-snug">{s.title}</p>
                  <p className="text-xs text-slate-400 mt-1 truncate">{s.url}</p>
                  {sourceScopeLabel(s.sourceScope) && (
                    <span className="inline-block mt-1.5 text-[11px] px-2 py-0.5 rounded-full font-medium bg-blue-50 text-blue-600">
                      {sourceScopeLabel(s.sourceScope)}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between border-t border-slate-100 pt-2.5">
                  {topic ? (
                    <span className="text-xs px-2.5 py-1 rounded-full font-medium" style={{ color: topic.color, background: topic.color + "20" }}>{topic.label}</span>
                  ) : <span className="text-xs text-slate-400">No topic</span>}
                  <span className="text-xs text-slate-400">{s.schedule ?? "One-time"}</span>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Add Source Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-slate-200 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-base font-semibold text-slate-900">Add a Source</h2>
                <p className="text-xs text-slate-500 mt-0.5">Synker will discover and ingest content automatically</p>
              </div>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400"><X className="size-4" /></button>
            </div>

            {/* Source Type Tabs */}
            <div className="flex gap-1 bg-slate-100 p-1 rounded-lg mb-5 w-fit">
              {["YouTube", "Website"].map((label) => (
                <button
                  key={label}
                  onClick={() => {
                    if (label === "YouTube") { setYoutubeParseMessage(""); setYoutubeParsedConfidence(null); }
                    else { setWebsiteKeyword(""); }
                  }}
                  className={`px-3 py-1.5 text-xs font-medium rounded transition-all ${label === "YouTube" && !showModal ? "bg-white text-slate-800 shadow-sm" : label === "Website" && !showModal ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* YouTube Section (Track B + Track A) */}
            <div className="space-y-4 mb-6">
              <div className="border-b border-slate-200 pb-4">
                <h3 className="text-sm font-semibold text-slate-800 mb-3">YouTube: Find & Create Notes</h3>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-slate-600 mb-1.5 block">Natural language query (optional)</label>
                    <input
                      value={youtubeParseMessage}
                      onChange={(e) => setYoutubeParseMessage(e.target.value)}
                      placeholder="e.g., 'Python tutorials for beginners, max 15 videos'"
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                    />
                    <button
                      onClick={handleYoutubeParseIntent}
                      disabled={youtubeParsePending || !youtubeParseMessage.trim()}
                      className="mt-2 text-xs px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {youtubeParsePending ? "Parsing…" : "Parse with AI"}
                    </button>
                    {youtubeParsedConfidence !== null && youtubeParsedConfidence < 0.6 && (
                      <Badge variant="warning" className="mt-2 inline-block">Low confidence — please confirm</Badge>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Search query</label>
                      <input
                        value={youtubeQuery}
                        onChange={(e) => setYoutubeQuery(e.target.value)}
                        placeholder="Search term"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Limit (1-50)</label>
                      <input
                        type="number"
                        value={youtubeLimit}
                        onChange={(e) => setYoutubeLimit(Math.max(1, Math.min(50, parseInt(e.target.value) || 10)))}
                        min="1"
                        max="50"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                      />
                    </div>
                  </div>
                  <Button
                    onClick={handleYoutubeSearch}
                    variant="secondary"
                    size="sm"
                    disabled={youtubeSearching || !youtubeQuery.trim()}
                    className="w-full justify-center"
                  >
                    <Search className="size-3" /> {youtubeSearching ? "Searching…" : "Search"}
                  </Button>
                </div>

                {youtubeSearchResults.length > 0 && (
                  <div className="mt-4 space-y-2 max-h-60 overflow-y-auto border border-slate-200 rounded-lg p-3 bg-slate-50">
                    <p className="text-xs font-medium text-slate-600">{youtubeSelected.size} selected</p>
                    {youtubeSearchResults.map((item) => (
                      <div key={item.video_id} className="flex items-start gap-2 p-2 bg-white rounded border border-slate-100 hover:border-blue-300 transition-colors">
                        <input
                          type="checkbox"
                          checked={youtubeSelected.has(item.video_id)}
                          onChange={() => toggleYoutubeSelect(item.video_id)}
                          className="mt-1 rounded"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-medium text-slate-800 line-clamp-2">{item.title}</p>
                          {item.channel && <p className="text-[11px] text-slate-500">{item.channel}</p>}
                        </div>
                        {youtubeBatchProcessing.has(item.url) && (
                          <Badge
                            variant={youtubeBatchProcessing.get(item.url) === "SUCCESS" ? "success" : youtubeBatchProcessing.get(item.url) === "ALREADY_EXISTS" ? "neutral" : "danger"}
                            className="shrink-0"
                          >
                            {youtubeBatchProcessing.get(item.url) === "PROCESSING" ? "…" : youtubeBatchProcessing.get(item.url)}
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {youtubeSelected.size > 0 && (
                  <Button
                    onClick={handleCreateNotesFromSelected}
                    variant="primary"
                    size="sm"
                    disabled={youtubeBatchProcessing.size > 0}
                    className="w-full justify-center mt-3"
                  >
                    Create Notes from {youtubeSelected.size} Selected
                  </Button>
                )}
              </div>

              <div className="border-b border-slate-200 pb-4">
                <h3 className="text-sm font-semibold text-slate-800 mb-3">YouTube: Subscribe & Monitor</h3>
                <div className="space-y-3">
                  <div className="flex gap-2 bg-slate-50 p-2 rounded-lg">
                    {["channel", "keyword"].map((mode) => (
                      <button
                        key={mode}
                        onClick={() => {
                          setYoutubeTrackAMode(mode as "channel" | "keyword");
                          setYoutubeTrackAUrl("");
                          setYoutubeTrackAKeyword("");
                        }}
                        className={`flex-1 px-2 py-1.5 text-xs font-medium rounded transition-all ${youtubeTrackAMode === mode ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
                      >
                        {mode === "channel" ? "Channel/Playlist" : "Keyword"}
                      </button>
                    ))}
                  </div>
                  {youtubeTrackAMode === "channel" ? (
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Channel or Playlist URL</label>
                      <input
                        value={youtubeTrackAUrl}
                        onChange={(e) => setYoutubeTrackAUrl(e.target.value)}
                        placeholder="https://youtube.com/@channel or playlist URL"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                      />
                    </div>
                  ) : (
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Keyword</label>
                      <input
                        value={youtubeTrackAKeyword}
                        onChange={(e) => setYoutubeTrackAKeyword(e.target.value)}
                        placeholder="e.g., Python tutorials"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                      />
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Limit (1-50)</label>
                      <input
                        type="number"
                        value={youtubeTrackALimit}
                        onChange={(e) => setYoutubeTrackALimit(Math.max(1, Math.min(50, parseInt(e.target.value) || 25)))}
                        min="1"
                        max="50"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Topic</label>
                      <select
                        value={youtubeTrackATopic}
                        onChange={(e) => setYoutubeTrackATopic(e.target.value)}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all bg-white"
                      >
                        <option value="">Uncategorised</option>
                        {(topics ?? []).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                      </select>
                    </div>
                  </div>
                  <Button
                    onClick={handleYoutubeTrackASave}
                    variant="primary"
                    size="sm"
                    disabled={youtubeTrackASaving || (!youtubeTrackAUrl && !youtubeTrackAKeyword)}
                    className="w-full justify-center"
                  >
                    {youtubeTrackASaving ? "Saving…" : "Save Source"}
                  </Button>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-slate-800 mb-3">Website: Subscribe & Monitor</h3>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-slate-600 mb-1.5 block">Keyword</label>
                    <input
                      value={websiteKeyword}
                      onChange={(e) => setWebsiteKeyword(e.target.value)}
                      placeholder="e.g., React best practices"
                      className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Limit (1-10)</label>
                      <input
                        type="number"
                        value={websiteLimit}
                        onChange={(e) => setWebsiteLimit(Math.max(1, Math.min(10, parseInt(e.target.value) || 5)))}
                        min="1"
                        max="10"
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-slate-600 mb-1.5 block">Topic</label>
                      <select
                        value={websiteTopic}
                        onChange={(e) => setWebsiteTopic(e.target.value)}
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all bg-white"
                      >
                        <option value="">Uncategorised</option>
                        {(topics ?? []).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                      </select>
                    </div>
                  </div>
                  <Button
                    onClick={handleWebsiteSave}
                    variant="primary"
                    size="sm"
                    disabled={websiteSaving || !websiteKeyword.trim()}
                    className="w-full justify-center"
                  >
                    {websiteSaving ? "Saving…" : "Save Source"}
                  </Button>
                </div>
              </div>
            </div>

            <div className="flex gap-2 pt-4 border-t border-slate-200">
              <Button onClick={() => setShowModal(false)} variant="secondary" className="flex-1 justify-center">Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Candidate Approval ───────────────────────────────────────────────────────

function CandidateApprovalScreen() {
  const { data: candidates, loading, refetch } = useApi(api.candidates.list);
  const { data: topics } = useApi(api.topics.list, seedTopics);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // AC-014, AC-015, AC-016: Helper to check if a candidate has been scored
  const isScoredCandidate = (c: Candidate): boolean =>
    c.qualityScore > 0 || c.confidenceScore > 0;

  const toggleExpand = (id: string) => setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleSelect = (id: string) => setSelected((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const pending = (candidates ?? []).filter((c) => c.status === "pending");

  function groupByTopic(items: Candidate[]) {
    const groups: Record<string, Candidate[]> = {};
    for (const c of items) {
      const key = c.topicId ?? "__uncategorised__";
      if (!groups[key]) groups[key] = [];
      groups[key].push(c);
    }
    return groups;
  }

  const [demo, setDemo] = useState(isDemoMode);
  useEffect(() => {
    const id = setInterval(() => setDemo(isDemoMode()), 2000);
    return () => clearInterval(id);
  }, []);

  const [acting, setActing] = useState<"approve" | "reject" | null>(null);
  async function handleBulkApprove() {
    if (acting || selected.size === 0) return;
    setActing("approve");
    try { await api.candidates.approve(Array.from(selected)); toast.success(`${selected.size} candidate(s) approved`); setSelected(new Set()); refetch(); }
    catch (e) { toast.error(`Approval failed: ${e instanceof Error ? e.message : "Request failed"}`); }
    finally { setActing(null); }
  }

  async function handleBulkReject() {
    if (acting || selected.size === 0) return;
    setActing("reject");
    try { await api.candidates.reject(Array.from(selected)); toast.success(`${selected.size} candidate(s) rejected`); setSelected(new Set()); refetch(); }
    catch (e) { toast.error(`Rejection failed: ${e instanceof Error ? e.message : "Request failed"}`); }
    finally { setActing(null); }
  }

  const groups = groupByTopic(pending);

  return (
    <div className="p-6 max-w-4xl space-y-5">
      <SectionHeader
        title="Review Candidates"
        description="AI has found these sources — review and approve them for processing"
        action={
          <div className="flex items-center gap-2">
            {selected.size > 0 && <span className="text-xs text-slate-500 font-medium">{selected.size} selected</span>}
            <Button size="sm" variant="secondary" onClick={() => selected.size === pending.length ? setSelected(new Set()) : setSelected(new Set(pending.map((c) => c.id)))}>
              {selected.size === pending.length ? "Deselect All" : "Select All"}
            </Button>
            <Button size="sm" variant="success" onClick={handleBulkApprove} disabled={selected.size === 0 || acting !== null || demo} title={demo ? "Backend offline" : undefined}>
              <CheckCircle2 className="size-3.5" /> {acting === "approve" ? "Approving…" : `Approve${selected.size > 0 ? ` (${selected.size})` : ""}`}
            </Button>
            <Button size="sm" variant="danger" onClick={handleBulkReject} disabled={selected.size === 0 || acting !== null || demo} title={demo ? "Backend offline" : undefined}>
              <XCircle className="size-3.5" /> {acting === "reject" ? "Rejecting…" : `Reject${selected.size > 0 ? ` (${selected.size})` : ""}`}
            </Button>
          </div>
        }
      />

      {loading ? (
        <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
      ) : pending.length === 0 ? (
        <Card className="p-8"><EmptyState icon={<CheckSquare className="size-6" />} title="Nothing to review" description="All candidates have been processed" /></Card>
      ) : (
        <div className="space-y-8">
          {Object.entries(groups).map(([topicId, items]) => {
            const topic = (topics ?? []).find((t) => t.id === topicId);
            return (
              <div key={topicId}>
                <div className="flex items-center gap-2.5 mb-3">
                  <div className="size-2.5 rounded-full" style={{ background: topic?.color ?? "#94a3b8" }} />
                  <h2 className="text-sm font-semibold text-slate-700">{topic?.label ?? "Uncategorised"}</h2>
                  <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">{items.length}</span>
                </div>
                <div className="space-y-2.5">
                  {items.map((c) => (
                    <Card key={c.id} className={`overflow-hidden transition-all ${selected.has(c.id) ? "ring-2 ring-blue-300" : ""}`}>
                      <div className="p-4">
                        <div className="flex items-start gap-3">
                          <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleSelect(c.id)}
                            className="mt-1 size-4 accent-blue-600 rounded cursor-pointer" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-3 flex-wrap">
                              <div className="min-w-0 flex-1">
                                <p className="text-sm font-semibold text-slate-800 leading-snug">{c.title}</p>
                                <p className="text-xs text-slate-400 mt-0.5">{c.sourceInfo}</p>
                              </div>
                              <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
                                <RecommendationBadge rec={c.recommendation} />
                                <StatusBadge status={c.status} />
                              </div>
                            </div>

                            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 mt-3">
                              {isScoredCandidate(c) ? (
                                <>
                                  {[
                                    { label: "Quality", value: c.qualityScore, warn: c.qualityScore < 60 },
                                    { label: "Confidence", value: c.confidenceScore, warn: false },
                                    { label: "Duplicate risk", value: c.duplicateScore, warn: c.duplicateScore > 50 },
                                  ].map(({ label, value, warn }) => (
                                    <div key={label} className="flex items-center gap-1.5">
                                      <span className="text-xs text-slate-400">{label}</span>
                                      <div className="flex items-center gap-1">
                                        <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                                          <div className={`h-full rounded-full ${warn ? "bg-amber-400" : "bg-blue-400"}`} style={{ width: `${value}%` }} />
                                        </div>
                                        <span className="text-xs font-medium text-slate-600">{value}</span>
                                      </div>
                                    </div>
                                  ))}
                                  <span className="text-xs text-slate-400">~{c.expectedNotes} notes</span>
                                  <span className="text-xs text-slate-400">~{c.estimatedTokens.toLocaleString()} tokens</span>
                                </>
                              ) : (
                                <>
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-xs text-slate-400">Quality</span>
                                    <span className="text-xs font-medium text-slate-400">—</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-xs text-slate-400">Confidence</span>
                                    <span className="text-xs font-medium text-slate-400">—</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-xs text-slate-400">Duplicate risk</span>
                                    <span className="text-xs font-medium text-slate-400">—</span>
                                  </div>
                                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-50 border border-slate-200">
                                    <span className="text-xs font-medium text-slate-500">Not scored</span>
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                          <button onClick={() => toggleExpand(c.id)}
                            className="shrink-0 flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors px-2 py-1 rounded-lg hover:bg-slate-100">
                            {expanded.has(c.id) ? <><EyeOff className="size-3.5" /> Hide</> : <><Eye className="size-3.5" /> Summary</>}
                          </button>
                        </div>
                      </div>
                      {expanded.has(c.id) && (
                        <div className="border-t border-slate-100 px-4 py-4 bg-slate-50">
                          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">AI Summary</p>
                          <p className="text-sm text-slate-600 leading-relaxed">{c.summary}</p>
                          <div className="flex flex-wrap gap-1.5 mt-3">
                            {c.extractedTopics.map((t) => (
                              <span key={t} className="text-xs px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-600">{t}</span>
                            ))}
                          </div>
                        </div>
                      )}
                    </Card>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Processing Jobs ──────────────────────────────────────────────────────────

function ProcessingJobsScreen() {
  const { data: jobs, loading, refetch } = useApi(api.jobs.list);
  const [filter, setFilter] = useState<"all" | Job["status"]>("all");
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());

  const [refreshing, setRefreshing] = useState(false);

  const hasRunning = (jobs ?? []).some((j) => j.status === "running");
  useEffect(() => {
    if (!hasRunning) return;
    const t = setInterval(() => refetch(), 5000);
    return () => clearInterval(t);
  }, [hasRunning, refetch]);

  const filtered = (jobs ?? []).filter((j) =>
    filter === "all" || j.status === filter || (filter === "completed" && j.status === "done")
  );
  const tabs: { key: "all" | Job["status"]; label: string; count?: number }[] = [
    { key: "all", label: "All", count: (jobs ?? []).length },
    { key: "running", label: "Running", count: (jobs ?? []).filter((j) => j.status === "running").length },
    { key: "queued", label: "Queued", count: (jobs ?? []).filter((j) => j.status === "queued").length },
    { key: "completed", label: "Completed", count: (jobs ?? []).filter((j) => j.status === "completed" || j.status === "done").length },
    { key: "failed", label: "Failed", count: (jobs ?? []).filter((j) => j.status === "failed").length },
  ];

  return (
    <div className="p-6 max-w-6xl space-y-5">
      <SectionHeader
        title="Processing Jobs"
        description="Track extraction, transcription, and note generation tasks"
        action={
          <Button onClick={async () => { setRefreshing(true); try { await refetch(); } finally { setRefreshing(false); } }} variant="secondary" size="sm" disabled={refreshing}>
            <RefreshCw className={`size-3.5${refreshing ? " animate-spin" : ""}`} /> {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />

      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setFilter(t.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${filter === t.key ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            {t.label}
            {(t.count ?? 0) > 0 && <span className={`px-1.5 py-0.5 rounded-full text-xs ${filter === t.key ? "bg-blue-100 text-blue-600" : "bg-slate-200 text-slate-500"}`}>{t.count}</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
      ) : (
        <Card className="overflow-hidden">
          {filtered.length === 0 ? (
            <EmptyState icon={<Cpu className="size-6" />} title="No jobs here" description="Jobs in this category will appear here" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[680px]">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    {["Source", "Job Type", "Status", "Progress", "Started", "Duration", ""].map((h) => (
                      <th key={h} className="text-left px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filtered.map((j) => (
                    <tr key={j.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-5 py-4">
                        <p className="text-sm font-medium text-slate-800 max-w-[220px] truncate">{j.sourceTitle}</p>
                        <p className="text-xs text-slate-400 font-mono mt-0.5">{j.id}</p>
                        {j.error && <p className="text-xs text-red-500 mt-1 line-clamp-1">{j.error}</p>}
                      </td>
                      <td className="px-5 py-4 text-sm text-slate-600 whitespace-nowrap">{j.type}</td>
                      <td className="px-5 py-4"><StatusBadge status={j.status} /></td>
                      <td className="px-5 py-4 w-40">
                        {j.status === "running" ? (
                          <div className="space-y-1">
                            <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                              <div className="h-full rounded-full bg-blue-500 transition-all duration-700" style={{ width: `${j.progress}%` }} />
                            </div>
                            <p className="text-xs text-slate-500 text-right">{j.progress}%</p>
                          </div>
                        ) : j.status === "completed" ? (
                          <div className="h-2 rounded-full bg-emerald-100 overflow-hidden"><div className="h-full rounded-full bg-emerald-400 w-full" /></div>
                        ) : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="px-5 py-4 text-xs text-slate-400 whitespace-nowrap">{formatDateTime(j.startedAt)}</td>
                      <td className="px-5 py-4 text-xs text-slate-400 whitespace-nowrap">{j.duration}</td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-1.5">
                          {j.status === "failed" && (
                            /cuda out of memory|oom|out of memory/i.test(j.error ?? "") ? (
                              <span className="text-xs text-amber-600 font-medium">Adjust model / device</span>
                            ) : (
                              <Button size="sm" variant="secondary" disabled={retryingIds.has(j.id)} onClick={async () => {
                                setRetryingIds((s) => { const n = new Set(s); n.add(j.id); return n; });
                                try { await api.jobs.retry(j.id); toast.success("Retrying"); refetch(); }
                                catch (e) { toast.error(`Retry failed: ${e instanceof Error ? e.message : "Request failed"}`); }
                                finally { setRetryingIds((s) => { const n = new Set(s); n.delete(j.id); return n; }); }
                              }}>
                                <RotateCcw className="size-3" /> {retryingIds.has(j.id) ? "Retrying…" : "Retry"}
                              </Button>
                            )
                          )}
                          {(j.status === "completed" || j.status === "done" || j.status === "failed") && (
                            <button
                              disabled={deletingIds.has(j.id)}
                              onClick={async () => {
                                setDeletingIds((s) => { const n = new Set(s); n.add(j.id); return n; });
                                try { await api.jobs.delete(j.id); toast.success("Job deleted"); refetch(); }
                                catch (e) { toast.error(`Delete failed: ${e instanceof Error ? e.message : "Request failed"}`); }
                                finally { setDeletingIds((s) => { const n = new Set(s); n.delete(j.id); return n; }); }
                              }}
                              className="p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors disabled:opacity-40"
                            >
                              <Trash2 className="size-3.5" />
                            </button>
                          )}
                          {j.artifactPath && <p className="text-xs text-blue-500 font-mono truncate max-w-[120px]">{j.artifactPath.split("/").pop()}</p>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

// ─── Knowledge Review ─────────────────────────────────────────────────────────

function KnowledgeReviewScreen() {
  const { data: notes, loading, refetch } = useApi(api.notes.list);
  // Selection is derived from the fetched list by id — never a stored Note object.
  // This keeps count, list, and detail from disagreeing: when a note leaves the
  // pending queue (accepted/rejected), it also disappears from the detail pane.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showReasoning, setShowReasoning] = useState(false);

  const selected = (notes ?? []).find((n) => n.id === selectedId) ?? null;

  useEffect(() => {
    const list = notes ?? [];
    if (list.length === 0) { setSelectedId(null); return; }
    if (!selectedId || !list.some((n) => n.id === selectedId)) setSelectedId(list[0].id);
  }, [notes, selectedId]);

  const [noteActing, setNoteActing] = useState<"approve" | "reject" | null>(null);
  async function handleApprove(id: string) {
    if (noteActing) return;
    setNoteActing("approve");
    try { await api.notes.approve(id); toast.success("Note accepted and added to vault"); }
    catch (e) { toast.error(`Failed to save note: ${e instanceof Error ? e.message : "Request failed"}`); }
    finally { setNoteActing(null); refetch(); }
  }
  async function handleReject(id: string) {
    if (noteActing) return;
    setNoteActing("reject");
    try { await api.notes.reject(id); toast.success("Note rejected"); }
    catch (e) { toast.error(`Failed to reject note: ${e instanceof Error ? e.message : "Request failed"}`); }
    finally { setNoteActing(null); refetch(); }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* List panel */}
      <div className="w-72 shrink-0 border-r border-slate-200 bg-white flex flex-col">
        <div className="px-4 py-4 border-b border-slate-100">
          <h1 className="text-base font-semibold text-slate-900">Knowledge Review</h1>
          <p className="text-xs text-slate-500 mt-0.5">{(notes ?? []).length} notes ready to review</p>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading
            ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 mx-3 my-2" />)
            : (notes ?? []).length === 0
              ? <EmptyState icon={<BookOpen className="size-5" />} title="No notes yet" />
              : (notes ?? []).map((n) => (
                <button key={n.id} onClick={() => { setSelectedId(n.id); setShowReasoning(false); }}
                  className={`w-full text-left px-4 py-3.5 border-b border-slate-100 transition-colors ${selected?.id === n.id ? "bg-blue-50 border-l-2 border-l-blue-500" : "hover:bg-slate-50"}`}>
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <AiActionBadge action={n.aiAction} />
                    {n.hasDuplicate && <Badge variant="warning"><AlertTriangle className="size-3" />Similar</Badge>}
                  </div>
                  <p className="text-sm font-medium text-slate-800 leading-snug line-clamp-2">{n.title}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <div className="flex items-center gap-1">
                      <div className="w-12 h-1 rounded-full bg-slate-100 overflow-hidden"><div className="h-full rounded-full bg-blue-400" style={{ width: `${n.qualityScore}%` }} /></div>
                    </div>
                    <span className="text-xs text-slate-400">Quality {n.qualityScore}</span>
                  </div>
                </button>
              ))}
        </div>
      </div>

      {/* Preview panel */}
      {selected ? (
        <div className="flex-1 overflow-y-auto bg-slate-50">
          <div className="p-6 space-y-5 max-w-4xl">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-xl font-bold text-slate-900">{selected.title}</h2>
                <p className="text-sm text-slate-500 mt-1">{selected.source}</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <Button onClick={() => handleReject(selected.id)} variant="danger" disabled={noteActing !== null}>
                  <XCircle className="size-4" /> {noteActing === "reject" ? "Rejecting…" : "Reject"}
                </Button>
                <Button onClick={() => handleApprove(selected.id)} variant="primary" disabled={noteActing !== null}>
                  <CheckCircle2 className="size-4" /> {noteActing === "approve" ? "Saving…" : "Accept & Save"}
                </Button>
              </div>
            </div>

            {selected.hasDuplicate && selected.similarTo && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="size-4 text-amber-500 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-amber-800">Similar content found</p>
                    <p className="text-xs text-amber-600">Matches "{selected.similarTo}" — review before accepting</p>
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button className="text-xs px-3 py-1.5 rounded-lg bg-amber-600 text-white hover:bg-amber-700 transition-colors font-medium">Merge Notes</button>
                  <button className="text-xs px-3 py-1.5 rounded-lg bg-white text-amber-700 border border-amber-200 hover:bg-amber-50 transition-colors font-medium">Keep Both</button>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
              <div className="xl:col-span-2 space-y-4">
                <Card className="p-5">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Note Preview</p>
                  <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(renderMarkdown(selected.content)) }} />
                </Card>

                <Card className="p-4">
                  <button onClick={() => setShowReasoning(!showReasoning)}
                    className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-800 transition-colors w-full font-medium">
                    {showReasoning ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    Why did the AI choose this action?
                  </button>
                  {showReasoning && (
                    <div className="mt-3 pt-3 border-t border-slate-100">
                      <p className="text-sm text-slate-600 leading-relaxed">{selected.similarityReasoning}</p>
                    </div>
                  )}
                </Card>
              </div>

              <div className="space-y-4">
                <Card className="p-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Note Metadata</p>
                  <div className="space-y-2">
                    {Object.entries(selected.frontmatter).map(([k, v]) => (
                      <div key={k} className="flex gap-2">
                        <span className="text-xs text-slate-400 font-mono shrink-0 pt-0.5 w-24 truncate">{k}</span>
                        <span className="text-xs text-slate-700 break-all leading-relaxed">{v}</span>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="p-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Sources Used</p>
                  <div className="space-y-2">
                    {selected.citations.map((c, i) => (
                      <p key={i} className="text-xs text-blue-600 font-mono truncate break-all">{c}</p>
                    ))}
                  </div>
                </Card>

                <Card className="p-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3 flex items-center gap-1.5">
                    <Link2 className="size-3.5" /> Linked Notes
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {selected.wikiLinks.map((l) => (
                      <span key={l} className="text-xs px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 border border-blue-100 hover:bg-blue-100 cursor-pointer transition-colors font-mono">
                        [[{l}]]
                      </span>
                    ))}
                  </div>
                </Card>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center bg-slate-50">
          <EmptyState icon={<BookOpen className="size-6" />} title="Select a note to review" description="Choose a note from the list to preview its content" />
        </div>
      )}
    </div>
  );
}

// ─── Vault Browser ────────────────────────────────────────────────────────────

function VaultBrowserScreen() {
  const { data: tree } = useApi(api.vault.tree, seedVaultTree);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileData, setFileData] = useState<VaultFile | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(["Indian Insurance", "Claude AI", "Backend Dev"]));
  const [search, setSearch] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  async function handleSelectFile(path: string) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setSelectedPath(path);
    try {
      const data = await api.vault.file(path);
      if (!controller.signal.aborted) setFileData(data);
    } catch {
      if (!controller.signal.aborted) toast.error("Could not load file");
    }
  }

  function toggleFolder(path: string) {
    setExpandedFolders((prev) => { const n = new Set(prev); n.has(path) ? n.delete(path) : n.add(path); return n; });
  }

  function matchesSearch(node: VaultNode): boolean {
    if (!search) return true;
    if (node.name.toLowerCase().includes(search.toLowerCase())) return true;
    return node.children?.some(matchesSearch) ?? false;
  }

  function renderTree(nodes: VaultNode[], depth = 0) {
    return nodes.filter(matchesSearch).map((n) => (
      <div key={n.path}>
        {n.type === "folder" ? (
          <>
            <button onClick={() => toggleFolder(n.path)} className="flex items-center gap-2 w-full text-left py-2 px-2 hover:bg-slate-100 transition-colors rounded-lg" style={{ paddingLeft: `${8 + depth * 14}px` }}>
              {expandedFolders.has(n.path) ? <ChevronDown className="size-3.5 text-slate-400 shrink-0" /> : <ChevronRight className="size-3.5 text-slate-400 shrink-0" />}
              <FolderOpen className="size-3.5 text-amber-500 shrink-0" />
              <span className="text-sm text-slate-700 font-medium truncate">{n.name}</span>
            </button>
            {expandedFolders.has(n.path) && n.children && renderTree(n.children, depth + 1)}
          </>
        ) : (
          <button onClick={() => handleSelectFile(n.path)}
            className={`flex items-center gap-2 w-full text-left py-1.5 px-2 hover:bg-slate-100 transition-colors rounded-lg ${selectedPath === n.path ? "bg-blue-50 text-blue-700" : "text-slate-600"}`}
            style={{ paddingLeft: `${22 + depth * 14}px` }}>
            <FileText className="size-3 shrink-0 text-slate-400" />
            <span className="text-xs truncate">{n.name}</span>
          </button>
        )}
      </div>
    ));
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Tree */}
      <div className="w-64 shrink-0 border-r border-slate-200 bg-white flex flex-col">
        <div className="p-3 border-b border-slate-100">
          <h1 className="text-sm font-semibold text-slate-900 mb-2">Vault Browser</h1>
          <div className="relative">
            <Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search your notes…"
              className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 outline-none focus:border-blue-300 transition-colors" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {tree && renderTree(tree)}
        </div>
      </div>

      {/* Content */}
      {fileData ? (
        <div className="flex-1 overflow-y-auto bg-slate-50">
          <div className="p-6 flex gap-5">
            <div className="flex-1 min-w-0 space-y-4">
              <p className="text-xs text-slate-400 font-mono">{fileData.path}</p>

              <Card className="overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-100 bg-slate-50">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Note Properties</p>
                </div>
                <div className="divide-y divide-slate-50">
                  {Object.entries(fileData.frontmatter).map(([k, v]) => (
                    <div key={k} className="flex items-start gap-4 px-5 py-2.5">
                      <span className="text-xs text-slate-400 font-mono w-28 shrink-0 pt-0.5">{k}</span>
                      <span className="text-xs text-slate-700">{v}</span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="p-5">
                <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(renderMarkdown(fileData.content)) }} />
              </Card>
            </div>

            {/* Meta rail */}
            <div className="w-44 shrink-0 space-y-3">
              <Card className="p-4">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">File Info</p>
                <div className="space-y-3">
                  {[
                    { label: "Words", value: fileData.wordCount },
                    { label: "Backlinks", value: fileData.backlinks },
                    { label: "Modified", value: new Date(fileData.lastModified).toLocaleDateString() },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <p className="text-xs text-slate-400">{label}</p>
                      <p className="text-sm font-semibold text-slate-700 mt-0.5">{value}</p>
                    </div>
                  ))}
                </div>
                <div className="border-t border-slate-100 mt-3 pt-3 space-y-2">
                  <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{fileData.graphNodeType}</span>
                  {fileData.cloudSafe
                    ? <div className="flex items-center gap-1.5 text-xs text-emerald-600"><Shield className="size-3" /> Cloud-safe</div>
                    : <div className="flex items-center gap-1.5 text-xs text-amber-600"><Shield className="size-3" /> Local only</div>}
                </div>
              </Card>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 bg-slate-50 flex items-center justify-center">
          <EmptyState icon={<FileText className="size-6" />} title="Select a file" description="Click any note in the tree to preview it" />
        </div>
      )}
    </div>
  );
}

// ─── Settings ─────────────────────────────────────────────────────────────────

// Defined at module scope, NOT inside SettingsScreen: a component defined inside
// another re-creates its function identity on every render, so React unmounts and
// remounts the whole subtree each keystroke — which is what stole input focus.
function SettingsToggle({ checked, onChange, label, description }: { checked: boolean; onChange: () => void; label: string; description?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div>
        <p className="text-sm font-medium text-slate-800">{label}</p>
        {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
      </div>
      <button onClick={onChange} className={`relative inline-flex h-6 w-11 rounded-full transition-colors shrink-0 focus:outline-none ${checked ? "bg-blue-600" : "bg-slate-200"}`}>
        <span className={`inline-block size-4 rounded-full bg-white shadow-sm transition-transform mt-1 ${checked ? "translate-x-6" : "translate-x-1"}`} />
      </button>
    </div>
  );
}

function SettingsSection({ title, description, children, onSave }: { title: string; description?: string; children: React.ReactNode; onSave: () => void }) {
  return (
    <Card className="p-6">
      <div className="mb-5">
        <h2 className="text-base font-semibold text-slate-900">{title}</h2>
        {description && <p className="text-sm text-slate-500 mt-0.5">{description}</p>}
      </div>
      <div className="space-y-4">{children}</div>
      <div className="mt-5 pt-4 border-t border-slate-100">
        <Button onClick={onSave} variant="primary" size="sm">Save changes</Button>
      </div>
    </Card>
  );
}

function SettingsScreen() {
  const { data: settings, loading: settingsLoading } = useApi(api.settings.get, seedSettings);
  const [vault, setVault] = useState(seedSettings.vault);
  const [ai, setAi] = useState(seedSettings.aiProviders);
  const [privacy, setPrivacy] = useState(seedSettings.privacy);
  const [discovery, setDiscovery] = useState(seedSettings.discovery);
  const [cleanup, setCleanup] = useState(seedSettings.cleanup);
  const [notifs, setNotifs] = useState(seedSettings.notifications);
  const [team, setTeam] = useState(seedSettings.team);
  const [claudeKey, setClaudeKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [showClaudeKey, setShowClaudeKey] = useState(false);
  const [showOpenaiKey, setShowOpenaiKey] = useState(false);
  const hasLoaded = useRef(false);

  useEffect(() => {
    if (settings && !hasLoaded.current) {
      hasLoaded.current = true;
      setVault(settings.vault);
      setAi(settings.aiProviders);
      setPrivacy(settings.privacy);
      setDiscovery(settings.discovery);
      setCleanup(settings.cleanup);
      setNotifs(settings.notifications);
      setTeam(settings.team);
    }
  }, [settings]);

  async function save(section: string, payload: unknown) {
    try {
      await api.settings.update(section, payload);
      toast.success("Settings saved");
    } catch (e) {
      toast.error(`Save failed: ${e instanceof Error ? e.message : "Request failed"}`);
    }
  }

  async function saveAiProviders() {
    if (claudeKey && !claudeKey.startsWith("sk-ant-")) { toast.error("Anthropic keys must start with sk-ant-"); return; }
    if (openaiKey && !openaiKey.startsWith("sk-")) { toast.error("OpenAI keys must start with sk-"); return; }
    const payload: AIProvidersWrite = { claudeKey: claudeKey || undefined, openaiKey: openaiKey || undefined, ollamaUrl: ai.ollamaUrl, fallbackOrder: ai.fallbackOrder };
    try {
      await api.settings.update("ai_providers", payload);
      toast.success("Settings saved");
      // Update key-set flags locally — no full refetch so other sections are not overwritten
      setAi(prev => ({
        ...prev,
        claudeKeySet: !!claudeKey || prev.claudeKeySet,
        openaiKeySet: !!openaiKey || prev.openaiKeySet,
      }));
      setClaudeKey("");
      setOpenaiKey("");
    } catch (e) {
      toast.error(`Save failed: ${e instanceof Error ? e.message : "Request failed"}`);
    }
  }

  const inputCls = "w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 bg-white transition-all placeholder:text-slate-400";
  const labelCls = "text-sm font-medium text-slate-700 mb-1.5 block";

  return (
    <div className="p-6 space-y-5 max-w-2xl">
      <SectionHeader title="Settings" description="Configure your vault, AI providers, and preferences" />

      <SettingsSection title="Vault" description="Where Synker writes your generated notes" onSave={() => save("vault", vault)}>
        <div><label className={labelCls}>Vault name</label><input className={inputCls} value={vault.name} onChange={(e) => setVault({ ...vault, name: e.target.value })} /></div>
        <div>
          <label className={labelCls}>Obsidian vault path</label>
          <input
            className={inputCls}
            value={vault.path}
            onChange={(e) => setVault({ ...vault, path: e.target.value })}
            placeholder="e.g. C:\Users\you\Documents\MyVault  or  /Users/you/Documents/MyVault"
          />
          <p className="text-xs text-slate-500 mt-1.5">
            Type the absolute path to your Obsidian vault folder. Approved notes will be written here as <code>.md</code> files under a <code>Synker/</code> subfolder.
            {" "}On Windows use backslashes (<code>C:\Users\…</code>); on Mac/Linux use forward slashes (<code>/Users/…</code>).
            {" "}If the backend runs on a remote server (Railway), notes are stored in the cloud vault browser above; to sync them to your local Obsidian install and run the <strong>Local Sync Bridge</strong> on your machine.
          </p>
        </div>
      </SettingsSection>

      <SettingsSection title="AI Providers" description="API keys and fallback order for note generation" onSave={saveAiProviders}>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Anthropic (Claude)</label>
            <div className="relative">
              <input type={showClaudeKey ? "text" : "password"} className={inputCls + " pr-10"} value={claudeKey} onChange={(e) => setClaudeKey(e.target.value)} placeholder={settingsLoading && !hasLoaded.current ? "Checking…" : ai.claudeKeySet ? "Key saved — enter new key to update" : "sk-ant-…"} />
              <button type="button" onClick={() => setShowClaudeKey(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors" tabIndex={-1}>
                {showClaudeKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>
          <div>
            <label className={labelCls}>OpenAI</label>
            <div className="relative">
              <input type={showOpenaiKey ? "text" : "password"} className={inputCls + " pr-10"} value={openaiKey} onChange={(e) => setOpenaiKey(e.target.value)} placeholder={settingsLoading && !hasLoaded.current ? "Checking…" : ai.openaiKeySet ? "Key saved — enter new key to update" : "sk-…"} />
              <button type="button" onClick={() => setShowOpenaiKey(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors" tabIndex={-1}>
                {showOpenaiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>
        </div>
        <div>
          <label className={labelCls}>Fallback order</label>
          <div className="flex gap-2">
            {ai.fallbackOrder.map((p, i) => (
              <div key={p} className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-700">
                <span className="text-slate-400 text-xs">{i + 1}.</span> {p}
              </div>
            ))}
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Privacy & Security" description="Control what data reaches cloud AI providers" onSave={() => save("privacy", privacy)}>
        <div>
          <label className={labelCls}>PII detection method</label>
          <select className={inputCls} value={privacy.piiMode} onChange={(e) => setPrivacy({ ...privacy, piiMode: e.target.value as "regex" | "ml" })}>
            <option value="regex">Regex patterns — fast, lightweight, no extra dependencies</option>
            <option value="ml">Local ML model — more accurate, requires more resources</option>
          </select>
        </div>
        <div className="border border-slate-200 rounded-xl divide-y divide-slate-100">
          <div className="px-4">
            <SettingsToggle checked={privacy.blockInsuranceData} onChange={() => setPrivacy({ ...privacy, blockInsuranceData: !privacy.blockInsuranceData })}
              label="Block insurance client data from cloud AI"
              description="Prevents policy numbers, Aadhaar, and PAN from being sent to external APIs" />
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Discovery Schedule" description="How often Synker checks each source for new content" onSave={() => save("discovery", discovery)}>
        <div className="grid grid-cols-2 gap-4">
          {([
            { label: "YouTube videos", key: "youtubeInterval", unit: "min" },
            { label: "Websites", key: "webInterval", unit: "min" },
            { label: "PDF documents", key: "pdfInterval", unit: "min" },
            { label: "Local folder debounce", key: "localDebounce", unit: "sec" },
          ] as { label: string; key: keyof typeof discovery; unit: string }[]).map(({ label, key, unit }) => (
            <div key={key}>
              <label className={labelCls}>{label} <span className="text-slate-400 font-normal">({unit})</span></label>
              <input type="number" className={inputCls} value={discovery[key]} onChange={(e) => setDiscovery({ ...discovery, [key]: Number(e.target.value) })} />
            </div>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection title="File Cleanup" description="What happens to downloaded files after notes are verified and published" onSave={() => save("cleanup", cleanup)}>
        <div className="grid grid-cols-2 gap-4">
          {(["youtube", "web", "pdf", "local"] as const).map((type) => (
            <div key={type}>
              <label className={labelCls}>{type === "youtube" ? "YouTube downloads" : type === "web" ? "Web cache" : type === "pdf" ? "PDF files" : "Local copies"}</label>
              <select className={inputCls} value={cleanup[type]} onChange={(e) => setCleanup({ ...cleanup, [type]: e.target.value as "keep" | "zip" | "delete" })}>
                <option value="keep">Keep original files</option>
                <option value="zip">Archive as ZIP</option>
                <option value="delete">Delete after verification</option>
              </select>
            </div>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection title="Notifications" description="How Synker alerts you when runs complete or fail" onSave={() => save("notifications", notifs)}>
        <div className="border border-slate-200 rounded-xl divide-y divide-slate-100 px-4">
          <SettingsToggle checked={notifs.desktop} onChange={() => setNotifs({ ...notifs, desktop: !notifs.desktop })} label="Desktop notifications" description="System notification when a pipeline run finishes" />
          <SettingsToggle checked={notifs.inApp} onChange={() => setNotifs({ ...notifs, inApp: !notifs.inApp })} label="In-app alerts" description="Badge and alert inside Synker" />
          <SettingsToggle checked={notifs.email} onChange={() => setNotifs({ ...notifs, email: !notifs.email })} label="Email notifications" description="Get emailed on run completion and failures" />
        </div>
        {notifs.email && (
          <div className="grid grid-cols-2 gap-4 pt-1">
            <div>
              <label className={labelCls}>Email provider</label>
              <select className={inputCls} value={notifs.emailProvider} onChange={(e) => setNotifs({ ...notifs, emailProvider: e.target.value as "resend" | "sendgrid" | "smtp" })}>
                <option value="resend">Resend</option>
                <option value="sendgrid">SendGrid</option>
                <option value="smtp">SMTP (custom)</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Send to</label>
              <input className={inputCls} type="email" value={notifs.emailAddress} onChange={(e) => setNotifs({ ...notifs, emailAddress: e.target.value })} placeholder="you@example.com" />
            </div>
          </div>
        )}
      </SettingsSection>

      <SettingsSection title="Team" description="Configure who has access to this Synker instance" onSave={() => save("team", team)}>
        <div>
          <label className={labelCls}>Team size</label>
          <select className={inputCls} value={team.tier} onChange={(e) => setTeam({ ...team, tier: e.target.value as "single" | "small" | "larger" })}>
            <option value="single">Just me (single user)</option>
            <option value="small">Small team — 2 to 5 people</option>
            <option value="larger">Larger team — 5 or more people</option>
          </select>
        </div>
        {team.tier !== "single" && (
          <div>
            <label className={labelCls}>Team members</label>
            <div className="rounded-xl border border-slate-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>{["Name", "Email", "Role"].map((h) => <th key={h} className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {team.members.map((m) => (
                    <tr key={m.id}>
                      <td className="px-4 py-3 text-slate-800 font-medium">{m.name}</td>
                      <td className="px-4 py-3 text-slate-500">{m.email}</td>
                      <td className="px-4 py-3"><Badge variant={m.role === "admin" ? "info" : m.role === "editor" ? "teal" : "neutral"}>{m.role}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </SettingsSection>
    </div>
  );
}

// ─── App Shell ────────────────────────────────────────────────────────────────

type Screen = "dashboard" | "sources" | "candidates" | "jobs" | "review" | "vault" | "settings";

const navItems: { id: Screen; label: string; description: string; icon: React.ReactNode }[] = [
  { id: "dashboard",  label: "Dashboard",  description: "Overview & status",   icon: <LayoutDashboard className="size-4" /> },
  { id: "sources",    label: "Sources",    description: "Manage sources",       icon: <Globe className="size-4" /> },
  { id: "candidates", label: "Approval",   description: "Review candidates",    icon: <CheckSquare className="size-4" /> },
  { id: "jobs",       label: "Jobs",       description: "Processing queue",     icon: <Cpu className="size-4" /> },
  { id: "review",     label: "Knowledge",  description: "Review generated notes", icon: <BookOpen className="size-4" /> },
  { id: "vault",      label: "Vault",      description: "Browse your notes",    icon: <FolderOpen className="size-4" /> },
  { id: "settings",   label: "Settings",   description: "Configure Synker",     icon: <Settings className="size-4" /> },
];

export default function App() {
  const { session, loading, signIn, signUp, signOut } = useAuth();
  const [active, setActive] = useState<Screen>("dashboard");
  const [demo, setDemo] = useState(false);

  // AC-011: Read URL on mount and set active screen
  useEffect(() => {
    const path = window.location.pathname;
    const pathToScreen: Record<string, Screen> = {
      "/approval": "candidates",
      "/candidates": "candidates",
      "/sources": "sources",
      "/jobs": "jobs",
      "/knowledge": "review",
      "/vault": "vault",
      "/settings": "settings",
      "/dashboard": "dashboard",
    };
    const mapped = pathToScreen[path];
    if (mapped) setActive(mapped);
  }, []);

  useEffect(() => {
    const t = setInterval(() => setDemo(isDemoMode()), 2000);
    return () => clearInterval(t);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-slate-100">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (!session) {
    return <LoginPage onSignIn={signIn} onSignUp={signUp} />;
  }

  const splitScreen = active === "review" || active === "vault";

  return (
    <div className="flex h-screen bg-slate-100 overflow-hidden" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
      <Toaster richColors position="bottom-right" />

      {/* Sidebar */}
      <aside className="w-56 shrink-0 flex flex-col" style={{ background: "var(--sidebar)" }}>
        {/* Logo */}
        <div className="px-5 py-5 border-b border-slate-700">
          <div className="flex items-center gap-2.5">
            <div className="size-8 rounded-xl bg-blue-500 flex items-center justify-center shrink-0 shadow-sm">
              <Zap className="size-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-white leading-tight">Synker</p>
              <p className="text-xs text-slate-400 leading-tight">Knowledge Platform</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setActive(item.id);
                // AC-013: Update URL when navigating via sidebar
                const pathMap: Record<Screen, string> = {
                  dashboard: "/dashboard",
                  sources: "/sources",
                  candidates: "/approval",
                  jobs: "/jobs",
                  review: "/knowledge",
                  vault: "/vault",
                  settings: "/settings",
                };
                const path = pathMap[item.id] || "/dashboard";
                window.history.pushState({}, "", path);
              }}
              className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm transition-all ${
                active === item.id
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-white hover:bg-slate-700"
              }`}
            >
              <span className="shrink-0">{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </button>
          ))}
        </nav>

        {/* Connection status */}
        <div className="px-4 py-3 border-t border-slate-700">
          {demo ? (
            <div className="flex items-center gap-2 text-xs text-amber-400">
              <WifiOff className="size-3.5 shrink-0" />
              <div>
                <p className="font-medium">Demo mode</p>
                <p className="text-amber-500/70">Backend not connected</p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-emerald-400">
              <Wifi className="size-3.5 shrink-0" />
              <div>
                <p className="font-medium">Connected</p>
                <p className="text-emerald-500/70 truncate max-w-[120px]">{BASE.replace(/^https?:\/\//, "").split("/")[0]}</p>
              </div>
            </div>
          )}
          <button
            onClick={signOut}
            className="text-xs text-slate-500 hover:text-slate-700 mt-2 transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className={`flex-1 min-w-0 ${splitScreen ? "flex flex-col overflow-hidden" : "overflow-y-auto"}`}>
        {demo && (
          <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center gap-2 text-sm text-amber-800 shrink-0">
            <WifiOff className="size-4 shrink-0" />
            Backend unavailable — showing cached preview. Changes disabled.
          </div>
        )}
        {active === "dashboard"  && <DashboardScreen onNavigateToSources={() => setActive("sources")} />}
        {active === "sources"    && <SourcesScreen />}
        {active === "candidates" && <CandidateApprovalScreen />}
        {active === "jobs"       && <ProcessingJobsScreen />}
        {active === "review"     && <div className="flex-1 overflow-hidden"><KnowledgeReviewScreen /></div>}
        {active === "vault"      && <div className="flex-1 overflow-hidden"><VaultBrowserScreen /></div>}
        {active === "settings"   && <SettingsScreen />}
      </main>
    </div>
  );
}







