import type { DashboardStats, ActivityEvent, Topic, Source, Candidate, Job, Note, VaultNode, VaultFile, Settings } from "../types";

export const seedStats: DashboardStats = {
  pendingApprovals: 6,
  activeJobs: 3,
  notesToday: 7,
  sourcesIndexed: 138,
  pipelineCounts: {
    Discover: 22,
    Analyze: 8,
    Approve: 14,
    Extract: 3,
    Transcribe: 1,
    Generate: 2,
    Verify: 1,
    Graphify: 0,
    Cleanup: 0,
  },
};

export const seedActivity: ActivityEvent[] = [
  { id: "a1", type: "approved", message: "Batch of 6 candidates approved — Indian Insurance topic", timestamp: "2 min ago" },
  { id: "a2", type: "merged", message: "Note merged: IRDAI Circular 2024 → existing Motor Insurance Overview", timestamp: "11 min ago" },
  { id: "a3", type: "created", message: "Note created: Claude 3.5 Sonnet Release Notes", timestamp: "24 min ago" },
  { id: "a4", type: "failed", message: "Transcription failed: job_b7e2d1 — Whisper OOM on 3h video", timestamp: "38 min ago" },
  { id: "a5", type: "synced", message: "Graphify sync complete — 4 nodes updated", timestamp: "1 hr ago" },
  { id: "a6", type: "indexed", message: "Local folder scanned: /docs/backend-references — 12 new files", timestamp: "1 hr ago" },
  { id: "a7", type: "created", message: "Note created: FastAPI Background Tasks Pattern", timestamp: "2 hr ago" },
  { id: "a8", type: "rejected", message: "Candidate rejected: Unrelated SEO article on car insurance", timestamp: "3 hr ago" },
];

export const seedTopics: Topic[] = [
  { id: "t1", label: "Indian Insurance", color: "#7c6af7" },
  { id: "t2", label: "Claude AI", color: "#06b6d4" },
  { id: "t3", label: "Backend Dev", color: "#10b981" },
  { id: "t4", label: "Python Tooling", color: "#f59e0b" },
];

export const seedSources: Source[] = [
  { id: "s1", type: "youtube", title: "IRDAI New Regulations 2024 — Full Breakdown", url: "https://youtube.com/watch?v=xKp2m3nQr8A", topicId: "t1", status: "done", addedAt: "2024-11-12T08:30:00Z", schedule: "daily" },
  { id: "s2", type: "web", title: "Anthropic Claude 3.5 Sonnet Release Blog", url: "https://anthropic.com/blog/claude-3-5-sonnet", topicId: "t2", status: "done", addedAt: "2024-11-11T14:20:00Z", schedule: null },
  { id: "s3", type: "pdf", title: "Motor Third Party Insurance Circular — IRDAI/HLT/GIC/CIR", url: "/local/irdai-mtp-circular.pdf", topicId: "t1", status: "processing", addedAt: "2024-11-12T09:00:00Z", schedule: null },
  { id: "s4", type: "local", title: "Backend Dev Reference Docs", url: "~/docs/backend-references", topicId: "t3", status: "done", addedAt: "2024-11-10T11:00:00Z", schedule: "every 30min" },
  { id: "s5", type: "web", title: "FastAPI Official Documentation — Background Tasks", url: "https://fastapi.tiangolo.com/tutorial/background-tasks/", topicId: "t3", status: "queued", addedAt: "2024-11-12T10:15:00Z", schedule: "weekly" },
  { id: "s6", type: "youtube", title: "Building AI Pipelines with LangGraph — Fireship", url: "https://youtube.com/watch?v=Lv9nGSbMn9Q", topicId: "t2", status: "failed", addedAt: "2024-11-11T17:45:00Z", schedule: null },
  { id: "s7", type: "pdf", title: "IRDAI Annual Report 2023-24", url: "/local/irdai-annual-2024.pdf", topicId: "t1", status: "queued", addedAt: "2024-11-12T09:45:00Z", schedule: null },
  { id: "s8", type: "web", title: "Ruff Python Linter — Configuration Guide", url: "https://docs.astral.sh/ruff/configuration/", topicId: "t4", status: "done", addedAt: "2024-11-09T16:00:00Z", schedule: null },
];

export const seedCandidates: Candidate[] = [
  {
    id: "c1", title: "IRDAI Master Circular on Health Insurance 2024", sourceInfo: "irdai.gov.in · Published Nov 8, 2024",
    domain: "irdai.gov.in", publishedAt: "Nov 8, 2024", topicId: "t1", recommendation: "process",
    qualityScore: 94, confidenceScore: 91, duplicateScore: 12, expectedNotes: 4, estimatedTokens: 3840,
    summary: "The IRDAI Master Circular consolidates all health insurance regulations effective from Jan 2025, covering standardised exclusions, claim settlement timelines, and policyholder grievance redressal. Key changes include mandatory 24hr cashless discharge and unified portability rules across all insurers.",
    extractedTopics: ["Health Insurance Regulation", "Cashless Claims", "Policyholder Rights", "IRDAI Compliance"],
    status: "pending",
  },
  {
    id: "c2", title: "Motor Insurance Premium Rating — Actuarial Methodology Update", sourceInfo: "irda.gov.in · Published Oct 28, 2024",
    domain: "irda.gov.in", publishedAt: "Oct 28, 2024", topicId: "t1", recommendation: "merge",
    qualityScore: 78, confidenceScore: 85, duplicateScore: 61, expectedNotes: 2, estimatedTokens: 1420,
    summary: "Updated premium rating methodology for motor third-party pools. Changes affect the risk weightings for commercial vehicles and introduce telematics-based discount eligibility. Overlaps significantly with existing Motor Insurance Overview note.",
    extractedTopics: ["Motor Insurance", "Premium Rating", "Actuarial Science", "Telematics"],
    status: "pending",
  },
  {
    id: "c3", title: "How Claude 3.5 Sonnet Handles Long Context Windows", sourceInfo: "youtube.com/@aiexplained · Nov 10, 2024",
    domain: "youtube.com", publishedAt: "Nov 10, 2024", topicId: "t2", recommendation: "process",
    qualityScore: 88, confidenceScore: 87, duplicateScore: 8, expectedNotes: 3, estimatedTokens: 2610,
    summary: "Detailed breakdown of Claude 3.5 Sonnet's 200k token context window, with benchmarks on retrieval accuracy at different document positions. Demonstrates practical uses for legal document analysis and code review across large codebases.",
    extractedTopics: ["Long Context", "Claude 3.5 Sonnet", "Retrieval Accuracy", "Benchmarks"],
    status: "pending",
  },
  {
    id: "c4", title: "FastAPI SQLAlchemy Async Pattern — Production Checklist", sourceInfo: "testdriven.io · Nov 5, 2024",
    domain: "testdriven.io", publishedAt: "Nov 5, 2024", topicId: "t3", recommendation: "process",
    qualityScore: 91, confidenceScore: 93, duplicateScore: 5, expectedNotes: 3, estimatedTokens: 2190,
    summary: "Comprehensive guide to async SQLAlchemy with FastAPI in production: connection pool sizing, session lifecycle management, Alembic migrations with async engine, and testing strategies. Includes common pitfalls with lazy loading in async contexts.",
    extractedTopics: ["FastAPI", "SQLAlchemy", "Async Python", "Production Patterns"],
    status: "pending",
  },
  {
    id: "c5", title: "Generic SEO Article — Compare Car Insurance Online", sourceInfo: "insurancewale.in · Nov 11, 2024",
    domain: "insurancewale.in", publishedAt: "Nov 11, 2024", topicId: null, recommendation: "skip",
    qualityScore: 22, confidenceScore: 31, duplicateScore: 18, expectedNotes: 0, estimatedTokens: 340,
    summary: "Low-quality SEO content targeting search keywords for car insurance comparison. No regulatory or analytical substance. Contains affiliate links and generic advice not specific to Indian market regulations.",
    extractedTopics: ["Car Insurance", "Comparison"],
    status: "pending",
  },
  {
    id: "c6", title: "Ruff v0.8 Release — New Rules and Performance Gains", sourceInfo: "astral.sh/blog · Nov 7, 2024",
    domain: "astral.sh", publishedAt: "Nov 7, 2024", topicId: "t4", recommendation: "review",
    qualityScore: 73, confidenceScore: 69, duplicateScore: 42, expectedNotes: 1, estimatedTokens: 890,
    summary: "Ruff v0.8 introduces 40 new lint rules, significant performance improvements (2x on large repos), and first-class support for PEP 695 type aliases. Review recommended to check overlap with existing Ruff Configuration note.",
    extractedTopics: ["Ruff", "Python Linting", "PEP 695", "Tooling"],
    status: "pending",
  },
];

export const seedJobs: Job[] = [
  { id: "job_a3f9b2", sourceTitle: "IRDAI Master Circular on Health Insurance 2024", type: "Extraction", status: "running", progress: 67, startedAt: "10:42 AM", duration: "1m 23s" },
  { id: "job_c1e8d4", sourceTitle: "How Claude 3.5 Sonnet Handles Long Context Windows", type: "Transcription", status: "running", progress: 31, startedAt: "10:43 AM", duration: "42s" },
  { id: "job_f2a7c9", sourceTitle: "FastAPI SQLAlchemy Async Pattern", type: "Note Gen", status: "running", progress: 88, startedAt: "10:40 AM", duration: "2m 51s" },
  { id: "job_b7e2d1", sourceTitle: "Building AI Pipelines with LangGraph", type: "Transcription", status: "failed", progress: 0, startedAt: "9:15 AM", duration: "—", error: "RuntimeError: CUDA out of memory. Whisper large-v3 requires 8GB VRAM; 5.2GB available." },
  { id: "job_d9k3m1", sourceTitle: "Motor Insurance Premium Rating Update", type: "Analysis", status: "completed", progress: 100, startedAt: "9:52 AM", duration: "3m 18s", artifactPath: "/tmp/synker/motor-rating-analysis.json" },
  { id: "job_e4p6n2", sourceTitle: "Ruff v0.8 Release", type: "PII Check", status: "completed", progress: 100, startedAt: "9:48 AM", duration: "8s", artifactPath: "/tmp/synker/ruff-v08-pii-clean.json" },
  { id: "job_g8r1t5", sourceTitle: "IRDAI Annual Report 2023-24", type: "Extraction", status: "queued", progress: 0, startedAt: "—", duration: "—" },
  { id: "job_h5v2x7", sourceTitle: "FastAPI Background Tasks Docs", type: "Analysis", status: "queued", progress: 0, startedAt: "—", duration: "—" },
];

export const seedNotes: Note[] = [
  {
    id: "n1", title: "Claude 3.5 Sonnet — Release Notes and Capabilities", source: "Anthropic Blog · Nov 11, 2024",
    generatedAt: "2024-11-11T15:30:00Z", aiAction: "created", qualityScore: 92, hasDuplicate: false,
    content: `## Overview\n\nClaude 3.5 Sonnet represents a significant capability jump in Anthropic's model family, achieving state-of-the-art performance on coding and reasoning benchmarks while maintaining the 200k token context window.\n\n## Key Improvements\n\n- **Coding**: Scores 49% on SWE-bench Verified, surpassing all publicly available models\n- **Vision**: Improved ability to interpret charts, graphs, and UI screenshots\n- **Speed**: 2x faster than Claude 3 Opus at 1/5th the cost\n\n## Context Window\n\nThe 200k token window enables ingestion of entire codebases, legal documents, or research corpora in a single prompt.\n\n## Use Cases for Synker\n\nIdeal for the note generation and analysis pipeline steps. Recommended as primary provider with GPT-4o as fallback.`,
    frontmatter: { title: "Claude 3.5 Sonnet — Release Notes", tags: "claude, anthropic, llm, release-notes", source: "https://anthropic.com/blog/claude-3-5-sonnet", created: "2024-11-11", status: "verified", quality_score: "92", moc: "AI Models", graph_node_type: "concept" },
    citations: ["https://anthropic.com/blog/claude-3-5-sonnet", "https://www.swebench.com/results"],
    wikiLinks: ["Claude AI", "LLM Benchmarks", "Anthropic", "AI Models MOC"],
    similarityReasoning: "No existing notes in the vault share significant semantic overlap with this content. The closest candidate was 'GPT-4o Overview' (similarity: 23%) — distinct enough to warrant a new note.",
  },
  {
    id: "n2", title: "IRDAI Motor Third-Party Insurance — Premium Rating 2024", source: "IRDAI Circular · Oct 28, 2024",
    generatedAt: "2024-11-12T09:05:00Z", aiAction: "merged", qualityScore: 84, hasDuplicate: true,
    content: `## Updated Rating Methodology\n\nThe October 2024 circular revises the actuarial basis for motor third-party pooling, effective Q1 2025.\n\n### Commercial Vehicle Changes\n\n- Goods carrying vehicles (GCV): risk weight increased by 12%\n- Passenger carrying vehicles (PCV): new telematics discount tier introduced\n\n### Telematics Eligibility\n\nPolicies with OBD-II telematics devices can qualify for up to 15% premium reduction after 6-month data collection period.\n\n## Integration with Existing Note\n\nThis content has been merged into the existing **Motor Insurance Overview** note, preserving prior sections on MTP pool structure.`,
    frontmatter: { title: "Motor Insurance — Premium Rating 2024 Update", tags: "insurance, motor, irdai, premium-rating", source: "https://irdai.gov.in/circulars/motor-tp-2024", created: "2024-11-12", status: "pending-review", quality_score: "84", moc: "Indian Insurance", graph_node_type: "regulation" },
    citations: ["https://irdai.gov.in/circulars/motor-tp-2024", "https://irdai.gov.in/annual-report-2024"],
    wikiLinks: ["Motor Insurance Overview", "IRDAI", "Indian Insurance MOC", "Premium Rating"],
    similarityReasoning: "Existing note 'Motor Insurance Overview' shows 68% semantic similarity. New content provides updated premium rates and telematics eligibility criteria not present in the existing note. Decision: merge new sections into existing note, preserve prior content.",
    similarTo: "Motor Insurance Overview",
  },
  {
    id: "n3", title: "FastAPI Async SQLAlchemy — Production Patterns", source: "testdriven.io · Nov 5, 2024",
    generatedAt: "2024-11-12T10:20:00Z", aiAction: "created", qualityScore: 89, hasDuplicate: false,
    content: `## Overview\n\nProduction-grade async SQLAlchemy integration with FastAPI requires careful attention to session lifecycle and connection pool configuration.\n\n## Session Lifecycle\n\n\`\`\`python\nasync def get_db() -> AsyncGenerator[AsyncSession, None]:\n    async with async_session_factory() as session:\n        try:\n            yield session\n            await session.commit()\n        except Exception:\n            await session.rollback()\n            raise\n\`\`\`\n\n## Pool Configuration\n\nFor production workloads, tune \`pool_size\` and \`max_overflow\` based on expected concurrency.\n\n## Testing\n\nUse \`pytest-asyncio\` with an in-memory SQLite async engine for unit tests.`,
    frontmatter: { title: "FastAPI Async SQLAlchemy — Production Patterns", tags: "fastapi, sqlalchemy, python, async, backend", source: "https://testdriven.io/blog/fastapi-sqlalchemy-async", created: "2024-11-12", status: "pending-review", quality_score: "89", moc: "Backend Dev", graph_node_type: "pattern" },
    citations: ["https://testdriven.io/blog/fastapi-sqlalchemy-async", "https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html"],
    wikiLinks: ["FastAPI", "SQLAlchemy", "Backend Dev MOC", "Async Python Patterns"],
    similarityReasoning: "No existing notes cover async SQLAlchemy patterns specifically. 'FastAPI Overview' note shares 19% similarity but focuses on routing concepts. Decision: create new dedicated note.",
  },
];

export const seedVaultTree: VaultNode[] = [
  {
    name: "Indian Insurance", path: "Indian Insurance", type: "folder", children: [
      { name: "Motor Insurance Overview.md", path: "Indian Insurance/Motor Insurance Overview.md", type: "file" },
      { name: "Health Insurance Regulations.md", path: "Indian Insurance/Health Insurance Regulations.md", type: "file" },
      { name: "IRDAI Motor TP Rating 2024.md", path: "Indian Insurance/IRDAI Motor TP Rating 2024.md", type: "file" },
    ]
  },
  {
    name: "Claude AI", path: "Claude AI", type: "folder", children: [
      { name: "Claude 3.5 Sonnet Release Notes.md", path: "Claude AI/Claude 3.5 Sonnet Release Notes.md", type: "file" },
      { name: "Claude API Reference.md", path: "Claude AI/Claude API Reference.md", type: "file" },
    ]
  },
  {
    name: "Backend Dev", path: "Backend Dev", type: "folder", children: [
      { name: "FastAPI Async SQLAlchemy.md", path: "Backend Dev/FastAPI Async SQLAlchemy.md", type: "file" },
      { name: "FastAPI Background Tasks.md", path: "Backend Dev/FastAPI Background Tasks.md", type: "file" },
      {
        name: "Patterns", path: "Backend Dev/Patterns", type: "folder", children: [
          { name: "Async Python Patterns.md", path: "Backend Dev/Patterns/Async Python Patterns.md", type: "file" },
        ]
      },
    ]
  },
  {
    name: "Python Tooling", path: "Python Tooling", type: "folder", children: [
      { name: "Ruff Configuration Guide.md", path: "Python Tooling/Ruff Configuration Guide.md", type: "file" },
    ]
  },
  { name: "MOC — AI Models.md", path: "MOC — AI Models.md", type: "file" },
  { name: "MOC — Indian Insurance.md", path: "MOC — Indian Insurance.md", type: "file" },
];

export const seedVaultFile: VaultFile = {
  path: "Claude AI/Claude 3.5 Sonnet Release Notes.md",
  content: `## Overview\n\nClaude 3.5 Sonnet represents a significant capability jump in Anthropic's model family.\n\n## Key Improvements\n\n- **Coding**: 49% on SWE-bench Verified\n- **Vision**: Improved chart and UI interpretation\n- **Speed**: 2x faster than Claude 3 Opus\n\n## Context Window\n\nThe 200k token window enables ingestion of entire codebases in a single prompt.\n\n## See Also\n\n- [[Claude API Reference]]\n- [[AI Models MOC]]`,
  frontmatter: { title: "Claude 3.5 Sonnet — Release Notes", tags: "claude, anthropic, llm", source: "https://anthropic.com/blog", created: "2024-11-11", status: "verified", quality_score: "92", moc: "AI Models", graph_node_type: "concept" },
  lastModified: "2024-11-12T08:30:00Z",
  wordCount: 187,
  backlinks: 3,
  graphNodeType: "concept",
  cloudSafe: true,
};

export const seedSettings: Settings = {
  vault: { path: "~/ObsidianVault/Synker", name: "Synker Vault" },
  aiProviders: { claudeKey: "sk-ant-••••••••••••••••", openaiKey: "sk-••••••••••••••••", ollamaUrl: "http://localhost:11434", fallbackOrder: ["claude", "openai"] },
  privacy: { piiMode: "regex", blockInsuranceData: true, cloudBlockList: ["client names", "policy numbers", "aadhaar", "PAN"] },
  discovery: { defaultInterval: 10, youtubeInterval: 60, webInterval: 10, pdfInterval: 30, localDebounce: 30 },
  cleanup: { youtube: "zip", web: "keep", pdf: "keep", local: "keep" },
  notifications: { desktop: true, inApp: true, email: false, emailProvider: "resend", emailAddress: "" },
  team: { tier: "single", members: [{ id: "u1", name: "Admin", email: "", role: "admin" }] },
};

