import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

export type RequirementFormat = "brief" | "template";
export type Role = "Student" | "Supervisor";

export type Task = {
  id: string;
  title: string;
  description: string;
  req_type: "FR" | "NFR";
  type_reason: string | null;
  complexity: number;
  complexity_reason: string | null;
  dependencies: string[];
  source: string;
  estimated_hours: number | null;
  estimated_days: number | null;
  recommended_team_size: number | null;
  skill_required: string | null;
  suggested_owner_role: string | null;
  risks: string[];
  estimation_breakdown: Record<string, unknown>;
  optional: boolean;
  confidence: "high" | "medium" | "low";
};

export type RiskItem = {
  category: string;
  severity: "critical" | "high" | "medium" | "low";
  message: string;
  mitigation: string;
  affected_tasks: string[];
  source: "rule" | "llm";
};

export type RiskReport = {
  risk_level: "low" | "medium" | "high" | "critical";
  risk_score: number;
  total_risks: number;
  risks: RiskItem[];
  mitigations: string[];
  generated_at: string;
};

export type LLMPlanningTrace = {
  role: string;
  attempted: boolean;
  accepted: boolean;
  used_fallback: boolean;
  fallback_reason: string | null;
  kb_enabled: boolean;
  retrieved_kb_context_chars: number;
  kb_document_count: number;
};

export type EffortSummary = {
  total_estimated_hours: number;
  total_estimated_days: number;
  fr_estimated_hours: number;
  nfr_estimated_hours: number;
};

export type SprintSummary = {
  sprint: number;
  name: string;
  goal: string;
  tasks: string[];
  total_estimated_hours: number;
  total_points: number;
  duration_weeks: number;
  owner_roles?: string[];
  focus_themes?: string[];
};

export type PlanSummary = {
  generated_at?: string;
  model?: string;
  provider?: string;
  generation_mode?: string;
  llm_used?: boolean;
  llm_attempted?: boolean;
  llm_accepted?: boolean;
  llm_model?: string;
  used_fallback?: boolean;
  fallback_reason?: string | null;
  retrieved_kb_context?: string;
  kb_document_count?: number;
  llm_planning_trace?: LLMPlanningTrace;
  critic?: { status?: string; score?: number; issues_count?: number; report_file?: string };
  input_file?: string;
  tasks_file?: string;
  graph_file?: string;
  pipeline_config?: {
    allow_fallback: boolean;
    allow_decomposition: boolean;
    force_fallback: boolean;
    use_kb: boolean;
  };
  plan_highlights?: Record<string, unknown>;
  effort_summary?: EffortSummary;
  team_allocation?: TeamMember[];
  risk_register?: Array<{ risk: string; task_count: number; task_ids: string[] }>;
  admin_review?: Record<string, unknown>;
  graph_analytics?: {
    fr_count?: number;
    nfr_count?: number;
    optional_task_count?: number;
    critical_path?: { task_ids?: string[] };
  };
  sprint_plan?: SprintSummary[];
};

export type MonitorReport = {
  overall_progress?: number;
  tasks_tracked?: number;
  tasks_completed?: number;
  tasks_in_progress?: number;
  tasks_not_started?: number;
  tasks_needs_review?: number;
  commits_analyzed?: number;
  task_progress?: Array<{
    task_id: string;
    task_title: string;
    status: "completed" | "in_progress" | "not_started" | "needs_review";
    matched_commits: string[];
    evidence?: string[];
    matched_files?: string[];
    match_reasons?: string[];
    evidence_confidence?: "none" | "low" | "medium" | "high";
    alignment_score?: number;
    evidence_note?: string | null;
    completion_estimate: number;
  }>;
  behind_schedule?: string[];
  unmatched_commits?: Array<{
    sha: string;
    message: string;
    author: string;
    date: string;
    files_changed?: string[];
  }>;
  repository_hotspots?: Array<{
    path: string;
    commit_count: number;
    linked_task_ids?: string[];
  }>;
  tracked_repository?: string | null;
  generated_at?: string;
};

export type DependencyGraph = {
  nodes?: Array<{ id: string; x?: number; y?: number; [key: string]: unknown }>;
  edges?: Array<{ source: string; target: string; [key: string]: unknown }>;
};

export type TechStackReport = {
  frontend: string[];
  backend: string[];
  database: string[];
  devops: string[];
  external_services: string[];
  detected_from?: string;
};

export type AllData = {
  tasks: { tasks: Task[]; tech_stack: TechStackReport | null } | null;
  summary: PlanSummary | null;
  risks: RiskReport | null;
  graph: DependencyGraph | null;
  monitor: MonitorReport | null;
};

export type AdminQueueItem = {
  task_id: string;
  title: string;
  source: string;
  confidence: string;
  optional: boolean;
  complexity: number;
  req_type: string;
  description: string;
  reason: string;
  dependencies: string[];
};

export type AdminQueue = {
  items: AdminQueueItem[];
  total: number;
  status: "pending" | "reviewed" | "empty" | "no_pipeline_run";
};

export type ReviewDecision = {
  task_id: string;
  action: "approved" | "edited" | "rejected" | "skipped";
  new_title?: string;
  note?: string;
};

export type ReviewResult = {
  status: string;
  kept_tasks: number;
  rejected_tasks: number;
  counts: { approved: number; edited: number; rejected: number; skipped: number };
  tasks_final_file: string;
};

export type TeamMember = {
  role: string;
  task_ids: string[];
  task_count: number;
  estimated_hours: number;
  focus: string;
};

export type CommitteeBrief = {
  domain_inference?: string;
  scope_assessment?: string;
  confidence_signal?: string;
  graph_summary?: string;
  ambiguity_register?: Array<{ task_id: string; reason: string; original_source: string }>;
  assumption_log?: string[];
};

export type BriefData = {
  committee_brief: CommitteeBrief;
  team_allocation: TeamMember[];
  risk_register: Array<{ risk: string; task_count: number; task_ids: string[] }>;
  effort_summary: { total_estimated_hours: number; total_estimated_days: number; fr_estimated_hours: number; nfr_estimated_hours: number };
  plan_highlights: Record<string, unknown>;
  admin_review?: Record<string, unknown>;
  critic?: { score?: number; status?: string };
  generated_at?: string;
  model?: string;
  generation_mode?: string;
};

export type EvalSample = {
  sample_id: string;
  description: string;
  passed: boolean;
  task_count: number;
  fr_count: number;
  nfr_count: number;
  optional_count: number;
  score: number;
  overall_score: number;
  req_coverage: number;
  coverage_score: number;
  classification_score: number;
  complexity_score: number;
  dependency_score: number;
  mmre: number;
  pred25: number;
  f1_fr: number;
  f1_nfr: number;
  used_fallback: boolean;
  error?: string;
};

export type EvaluationReport = {
  overall_score: number;
  system_score: number;
  pass_rate: number;
  sample_count: number;
  samples: EvalSample[];
  generated_at?: string;
};

export type AblationCondition = {
  condition: string;
  average_coverage_score?: number | null;
  average_overall_score?: number | null;
  average_mmre?: number | null;
  average_pred25?: number | null;
  average_f1_fr?: number | null;
  average_f1_nfr?: number | null;
  avg_f1_fr?: number | null;
  avg_f1_nfr?: number | null;
  pass_rate?: number | null;
};

export type AblationReport = {
  generated_at?: string;
  total_samples?: number;
  llm_available?: boolean;
  llm_conditions_requested?: boolean;
  llm_conditions_skipped?: boolean;
  conditions?: Record<string, AblationCondition>;
  delta_R_to_K_overall?: number | null;
  delta_R_to_L_overall?: number | null;
};

export type KBStats = {
  count: number;
  collection_name: string;
  status: "ready" | "empty";
};

export type KBResult = {
  text: string;
  metadata: Record<string, unknown>;
  category: string;
  distance: number;
};

export type ChatMessage = {
  id: string;
  role: Role;
  type: string;
  text: string;
  created_at: string;
};

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
});

function toApiErrorMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    if (error.code === "ERR_NETWORK" || error.message === "Network Error") {
      return `Cannot reach backend API at ${API_BASE_URL}. Keep start.bat running, then refresh the page.`;
    }
    if (error.response?.data && typeof error.response.data === "object" && "detail" in error.response.data) {
      return String(error.response.data.detail);
    }
    if (error.response?.status) {
      return `API request failed with status ${error.response.status}.`;
    }
  }
  return error instanceof Error ? error.message : "API request failed.";
}

export async function getHealth() {
  const { data } = await client.get<{ status: string; version: string }>("/health");
  return data;
}

export async function getAllData() {
  const { data } = await client.get<AllData>("/data/all");
  return data;
}

export async function runPipeline(payload: {
  requirements: string;
  input_format: RequirementFormat;
  use_kb: boolean;
  allow_fallback?: boolean;
}) {
  try {
    const { data } = await client.post<{ status: string }>("/pipeline/run", {
      ...payload,
      allow_fallback: payload.allow_fallback ?? true,
    });
    return data;
  } catch (error) {
    throw new Error(toApiErrorMessage(error));
  }
}

export async function getPipelineStatus() {
  const { data } = await client.get<Record<string, unknown>>("/pipeline/status");
  return data;
}

export async function getPipelineInput() {
  const { data } = await client.get<{ text: string; source: string }>("/pipeline/input");
  return data;
}

export function pipelineEventsUrl() {
  return `${API_BASE_URL}/pipeline/events`;
}

export async function analyzeMonitor(repoPath?: string) {
  const { data } = await client.post<MonitorReport>("/monitor/analyze", {
    repo_path: repoPath || null,
    use_semantic: true,
  });
  return data;
}

export async function getChatMessages() {
  const { data } = await client.get<{
    messages: ChatMessage[];
    plan_status: string;
  }>("/chat/messages");
  return data;
}

export async function sendChatMessage(role: Role, text: string) {
  const { data } = await client.post<ChatMessage>("/chat/messages", { role, text });
  return data;
}

export async function clearChatMessages(): Promise<void> {
  await client.delete("/chat/messages");
}

export async function approvePlan(comment: string) {
  const { data } = await client.post<ChatMessage>("/chat/approve", {
    role: "Supervisor",
    comment,
  });
  return data;
}

export async function rejectPlan(comment: string) {
  const { data } = await client.post<ChatMessage>("/chat/reject", {
    role: "Supervisor",
    comment,
  });
  return data;
}

export async function getAdminQueue() {
  const { data } = await client.get<AdminQueue>("/admin/queue");
  return data;
}

export async function submitReview(decisions: ReviewDecision[]) {
  const { data } = await client.post<ReviewResult>("/admin/review", { decisions });
  return data;
}

export async function getBrief() {
  const { data } = await client.get<BriefData>("/data/brief");
  return data;
}

export async function getEvaluationResults() {
  const { data } = await client.get<{ report: Record<string, unknown>; ablation: AblationReport | null; running: boolean }>("/evaluate/results");
  const rawReport = data.report;
  const metricSummary = (rawReport.metric_summary ?? {}) as Record<string, unknown>;
  const samples = (rawReport.samples ?? rawReport.results ?? []) as EvalSample[];
  return {
    ...data,
    report: {
      ...rawReport,
      overall_score: Number(rawReport.overall_score ?? metricSummary.overall_system_score ?? 0),
      system_score: Number(rawReport.system_score ?? metricSummary.overall_system_score ?? 0),
      pass_rate: Number(rawReport.pass_rate ?? (Number(rawReport.pass_rate_pct ?? 0) / 100)),
      sample_count: Number(rawReport.sample_count ?? rawReport.total_samples ?? samples.length),
      samples,
      generated_at: String(rawReport.generated_at ?? rawReport.evaluated_at ?? ""),
    } as EvaluationReport,
  };
}

export async function runEvaluation() {
  const { data } = await client.post<{ status: string; message: string }>("/evaluate/run");
  return data;
}

export async function getKBStats() {
  const { data } = await client.get<KBStats>("/kb/stats");
  return data;
}

export async function searchKB(query: string, n_results = 5) {
  const { data } = await client.post<{ query: string; results: KBResult[]; count: number }>("/kb/search", { query, n_results });
  return data;
}

export type ExplainRequest = {
  context_type: "task" | "risk" | "critic";
  item_id: string;
  question?: string;
};

export type ExplainResponse = {
  explanation: string;
  item_id: string;
  context_type: string;
};

export async function explainItem(req: ExplainRequest): Promise<ExplainResponse> {
  const { data } = await client.post<ExplainResponse>("/ai/explain", req, { timeout: 90_000 });
  return data;
}
