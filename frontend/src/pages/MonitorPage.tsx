import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Circle,
  Clock,
  Flame,
  FolderGit2,
  GitCommit,
  ShieldCheck,
} from "lucide-react";

import { analyzeMonitor } from "../lib/api";
import { DEMO_ALL_DATA } from "../lib/demoProject";
import { buildExecutionRoadmap, buildPresentationTasks } from "../lib/presentation";
import { useAppStore } from "../lib/store";

type TaskProgress = {
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
};

type FullMonitorReport = {
  overall_progress: number;
  tasks_tracked: number;
  tasks_completed: number;
  tasks_in_progress: number;
  tasks_not_started: number;
  tasks_needs_review?: number;
  commits_analyzed: number;
  task_progress: TaskProgress[];
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

const STATUS_META = {
  completed: { icon: CheckCircle, color: "#4ade80", bg: "rgba(22,163,74,0.15)", label: "Completed" },
  in_progress: { icon: Clock, color: "#0ea5e9", bg: "rgba(14,165,233,0.15)", label: "In Progress" },
  needs_review: { icon: AlertTriangle, color: "#f59e0b", bg: "rgba(245,158,11,0.15)", label: "Needs Review" },
  not_started: { icon: Circle, color: "#64748b", bg: "rgba(71,85,105,0.15)", label: "Not Started" },
};

const CONFIDENCE_META = {
  high: { label: "Verified Evidence", color: "#4ade80", bg: "rgba(22,163,74,0.15)" },
  medium: { label: "Partial Evidence", color: "#38bdf8", bg: "rgba(56,189,248,0.14)" },
  low: { label: "ID Match Only", color: "#f59e0b", bg: "rgba(245,158,11,0.15)" },
  none: { label: "No Evidence", color: "#64748b", bg: "rgba(71,85,105,0.15)" },
} as const;

const DEMO_MONITOR_VIEW: FullMonitorReport = {
  overall_progress: 0.58,
  tasks_tracked: 18,
  tasks_completed: 3,
  tasks_in_progress: 2,
  tasks_not_started: 13,
  tasks_needs_review: 1,
  commits_analyzed: 18,
  behind_schedule: ["T005", "T008"],
  task_progress: (DEMO_ALL_DATA.tasks?.tasks ?? []).map((task, index) => ({
    task_id: task.id,
    task_title: task.title,
    status: index < 3 ? "completed" : index < 5 ? "in_progress" : index === 5 ? "needs_review" : "not_started",
    matched_commits: index < 5 ? [`demo-${index + 1}a`, `demo-${index + 1}b`].slice(0, index < 3 ? 2 : 1) : [],
    evidence: index < 5
      ? [
          `Implemented milestone for ${task.title.toLowerCase()}.`,
          `Refined workflow details for ${task.id}.`,
        ].slice(0, index < 3 ? 2 : 1)
      : [],
    matched_files: index < 5
      ? [`src/${task.id.toLowerCase()}_${task.title.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 28)}.ts`]
      : [],
    match_reasons: index < 3 ? ["task reference", "keyword"] : index < 5 ? ["keyword"] : [],
    evidence_confidence: index < 3 ? "high" : index < 5 ? "medium" : index === 5 ? "low" : "none",
    alignment_score: index < 3 ? 0.82 : index < 5 ? 0.58 : index === 5 ? 0.19 : 0,
    evidence_note: index === 5
      ? "Task ID was found, but the repository wording and changed files do not strongly align with this task."
      : index < 5 && index >= 3
        ? "Repository evidence is partially aligned; manual validation is recommended before treating this task as complete."
        : null,
    completion_estimate: index < 3 ? 1 : index < 5 ? 0.55 : 0,
  })),
  unmatched_commits: [
    {
      sha: "demo-unmatched-01",
      message: "Refactor shared form shell and cleanup old helper wiring",
      author: "committee.demo",
      date: "2026-05-27T11:40:00+00:00",
      files_changed: ["src/shared/form-shell.tsx", "src/lib/legacy-helper.ts"],
    },
    {
      sha: "demo-unmatched-02",
      message: "Draft analytics export prototype outside approved baseline",
      author: "committee.demo",
      date: "2026-05-27T12:05:00+00:00",
      files_changed: ["src/research/export-spike.ts"],
    },
  ],
  repository_hotspots: [
    {
      path: "src/backend/t005_billing_claims_workflow.ts",
      commit_count: 4,
      linked_task_ids: ["T005"],
    },
    {
      path: "src/portal/t006_patient_portal.tsx",
      commit_count: 3,
      linked_task_ids: ["T006", "T008"],
    },
  ],
  tracked_repository: "case_study",
};

function toMonitorError(error: unknown) {
  if (typeof error === "object" && error !== null) {
    const maybeAxios = error as { response?: { data?: { detail?: string } }; message?: string };
    return maybeAxios.response?.data?.detail ?? maybeAxios.message ?? "Monitor failed";
  }
  return "Monitor failed";
}

function trackingTone(coverage: number, criticalCoverage: number, behindCount: number) {
  if (coverage >= 60 && criticalCoverage >= 50 && behindCount <= 2) {
    return {
      label: "Strong traceability",
      color: "#4ade80",
      bg: "rgba(74,222,128,0.14)",
      detail: "Repository evidence is keeping pace with the planned baseline and the critical chain already has visible implementation signals.",
    };
  }
  if (coverage >= 35) {
    return {
      label: "Developing traceability",
      color: "#38bdf8",
      bg: "rgba(56,189,248,0.14)",
      detail: "The repository is showing meaningful execution evidence, but several planned tasks still need stronger commit coverage.",
    };
  }
  return {
    label: "Weak traceability",
    color: "#f97316",
    bg: "rgba(249,115,22,0.14)",
    detail: "The repository does not yet provide enough commit evidence to defend the baseline as actively tracked execution.",
  };
}

function phaseTone(evidenceCoverage: number, behindCount: number) {
  if (evidenceCoverage >= 0.75 && behindCount === 0) return { label: "Well tracked", color: "#4ade80" };
  if (evidenceCoverage >= 0.4) return { label: "Emerging evidence", color: "#38bdf8" };
  return { label: "Needs evidence", color: "#f97316" };
}

function repositoryGatePosture(isLive: boolean, coverage: number, commits: number) {
  if (coverage >= 60 && commits >= 8) {
    return {
      label: isLive ? "Live gate active" : "Evidence gate active",
      detail: "The repository is already producing enough traceable evidence to defend that delivery is being tracked against the approved baseline.",
    };
  }
  if (coverage >= 35 || commits >= 4) {
    return {
      label: isLive ? "Live gate building" : "Evidence gate building",
      detail: "Repository tracking is active, but the committee should treat the current snapshot as growing evidence rather than complete execution coverage.",
    };
  }
  return {
    label: isLive ? "Live gate warming up" : "Evidence gate warming up",
    detail: "The page is connected to the repository baseline, but more commit evidence is still needed before the gate looks mature in front of the committee.",
  };
}

function formatSnapshot(value: string | undefined) {
  if (!value) return "Current session snapshot";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function defaultExpandedTaskId(report: FullMonitorReport | null) {
  if (!report?.task_progress?.length) return null;
  return report.task_progress.find((item) => item.matched_commits.length > 0)?.task_id
    ?? report.task_progress[0]?.task_id
    ?? null;
}

function formatTrackingReason(reason: string) {
  return reason
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function isTrustedEvidence(progress: TaskProgress) {
  return progress.evidence_confidence === "high" || progress.evidence_confidence === "medium";
}

function confidenceRank(confidence?: TaskProgress["evidence_confidence"]) {
  if (confidence === "high") return 3;
  if (confidence === "medium") return 2;
  if (confidence === "low") return 1;
  return 0;
}

function alignmentPercent(progress: TaskProgress) {
  return Math.round((progress.alignment_score ?? 0) * 100);
}

export default function MonitorPage() {
  const [repoPath, setRepoPath] = useState("");
  const [report, setReport] = useState<FullMonitorReport | null>(DEMO_MONITOR_VIEW);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const autoAnalyzeStarted = useRef(false);

  const storeMonitor = useAppStore((s) => s.data?.monitor);
  const summary = useAppStore((s) => s.data?.summary ?? DEMO_ALL_DATA.summary);
  const rawTasks = useAppStore((s) => s.data?.tasks?.tasks?.length ? s.data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? []);
  const tasks = useMemo(() => buildPresentationTasks(rawTasks), [rawTasks]);
  const roadmap = useMemo(() => buildExecutionRoadmap(tasks), [tasks]);
  const usingDemo = !storeMonitor;

  useEffect(() => {
    if (storeMonitor) {
      const nextReport = storeMonitor as unknown as FullMonitorReport;
      setReport(nextReport);
      setExpandedTask(defaultExpandedTaskId(nextReport));
    }
  }, [storeMonitor]);

  useEffect(() => {
    if (!storeMonitor || autoAnalyzeStarted.current || loading) return;
    const snapshot = storeMonitor as unknown as FullMonitorReport;
    const hasEvidence = (snapshot.task_progress ?? []).some((item) => item.matched_commits.length > 0);
    if ((snapshot.commits_analyzed ?? 0) > 0 || hasEvidence) return;

    autoAnalyzeStarted.current = true;
    setLoading(true);
    setError("");

    void analyzeMonitor().then((result) => {
      const nextReport = result as unknown as FullMonitorReport;
      setReport(nextReport);
      setExpandedTask(defaultExpandedTaskId(nextReport));
    }).catch((monitorError) => {
      setError(toMonitorError(monitorError));
      autoAnalyzeStarted.current = false;
    }).finally(() => {
      setLoading(false);
    });
  }, [loading, storeMonitor]);

  async function analyze() {
    setLoading(true);
    setError("");
    setReport(null);
    setExpandedTask(null);
    try {
      const result = await analyzeMonitor(repoPath.trim() || undefined) as unknown as FullMonitorReport;
      setReport(result);
      setExpandedTask(defaultExpandedTaskId(result));
    } catch (monitorError) {
      setError(toMonitorError(monitorError));
      setReport(DEMO_MONITOR_VIEW);
      setExpandedTask(defaultExpandedTaskId(DEMO_MONITOR_VIEW));
    } finally {
      setLoading(false);
    }
  }

  const criticalIds = summary?.graph_analytics?.critical_path?.task_ids ?? [];
  const reportProgress = report?.task_progress ?? [];
  const taskDetailsById = useMemo(() => new Map(tasks.map((task) => [task.id, task])), [tasks]);
  const progressMap = new Map(reportProgress.map((item) => [item.task_id, item]));
  const highConfidenceTasks = reportProgress.filter((item) => item.evidence_confidence === "high").length;
  const partialEvidenceTasks = reportProgress.filter((item) => item.evidence_confidence === "medium").length;
  const verifiedTasks = reportProgress.filter((item) => isTrustedEvidence(item)).length;
  const reviewTasks = reportProgress.filter((item) => item.status === "needs_review").length;
  const evidenceCoverage = tasks.length ? Math.round((verifiedTasks / tasks.length) * 100) : 0;
  const totalEvidenceCommits = reportProgress.reduce((sum, item) => sum + item.matched_commits.length, 0);
  const criticalCovered = criticalIds.filter((taskId) => {
    const progress = progressMap.get(taskId);
    return progress ? isTrustedEvidence(progress) : false;
  }).length;
  const criticalCoverage = criticalIds.length ? Math.round((criticalCovered / criticalIds.length) * 100) : 0;
  const tone = trackingTone(evidenceCoverage, criticalCoverage, report?.behind_schedule?.length ?? 0);
  const persistedRepository = report?.tracked_repository?.trim() ?? "";
  const trackedRepository = persistedRepository
    ? persistedRepository
    : repoPath.trim()
    ? repoPath.trim()
    : usingDemo
      ? "Committee demo repository (case_study)"
      : "Latest analyzed repository from the backend session";
  const trackingMode = repoPath.trim()
    ? "Live Git repository path"
    : usingDemo
      ? "Committee demo evidence snapshot"
      : "Stored backend tracking snapshot";
  const lastSnapshot = formatSnapshot(report?.generated_at);
  const gatePosture = repositoryGatePosture(Boolean(repoPath.trim()), evidenceCoverage, totalEvidenceCommits);
  const unmatchedCommits = report?.unmatched_commits ?? [];
  const repositoryHotspots = report?.repository_hotspots ?? [];

  const strongestEvidenceTask = reportProgress
    .slice()
    .sort((left, right) => {
      if (confidenceRank(right.evidence_confidence) !== confidenceRank(left.evidence_confidence)) {
        return confidenceRank(right.evidence_confidence) - confidenceRank(left.evidence_confidence);
      }
      if (right.matched_commits.length !== left.matched_commits.length) {
        return right.matched_commits.length - left.matched_commits.length;
      }
      return (right.completion_estimate ?? 0) - (left.completion_estimate ?? 0);
    })[0];

  const phaseSnapshots = roadmap.map((phase) => {
    const phaseItems = phase.tasks
      .map((task) => progressMap.get(task.id))
      .filter((item): item is TaskProgress => Boolean(item));
    const evidenceTasks = phaseItems.filter((item) => isTrustedEvidence(item)).length;
    const evidenceCommits = phaseItems.reduce((sum, item) => sum + item.matched_commits.length, 0);
    const behind = (report?.behind_schedule ?? []).filter((taskId) => phase.tasks.some((task) => task.id === taskId));
    const toneMeta = phaseTone(phase.tasks.length ? evidenceTasks / phase.tasks.length : 0, behind.length);
    return {
      ...phase,
      evidenceTasks,
      evidenceCommits,
      behind,
      toneMeta,
    };
  });

  const phaseByTaskId = new Map(
    phaseSnapshots.flatMap((phase) => phase.tasks.map((task) => [task.id, phase.title] as const)),
  );

  const orderedEvidenceTasks = reportProgress
    .map((progress) => {
      const task = taskDetailsById.get(progress.task_id);
      return {
        id: progress.task_id,
        title: task?.title ?? progress.task_title ?? progress.task_id,
        reqType: task?.req_type ?? null,
        ownerRole: task?.suggested_owner_role ?? "Unassigned",
        progress,
        phase: phaseByTaskId.get(progress.task_id) ?? "Tracked task",
      };
    })
    .sort((left, right) => {
      if (confidenceRank(right.progress.evidence_confidence) !== confidenceRank(left.progress.evidence_confidence)) {
        return confidenceRank(right.progress.evidence_confidence) - confidenceRank(left.progress.evidence_confidence);
      }
      if (right.progress.matched_commits.length !== left.progress.matched_commits.length) {
        return right.progress.matched_commits.length - left.progress.matched_commits.length;
      }
      return right.progress.completion_estimate - left.progress.completion_estimate;
    });

  return (
    <div className="fade-up">
      <h1 className="page-title">
        <Activity size={22} /> Repository Gate
      </h1>
      <p className="page-sub">Committee-facing repository gate showing whether the approved student baseline is leaving traceable Git evidence across execution, dependencies, and critical release checkpoints.</p>

      {usingDemo && (
        <div
          style={{
            marginBottom: 14,
            borderRadius: 12,
            padding: "12px 16px",
            border: "1px solid rgba(59,130,246,0.25)",
            background: "rgba(59,130,246,0.08)",
            color: "#bfdbfe",
            fontSize: 13,
          }}
        >
          Live repository evidence is unavailable, so this tab is showing the committee demo tracking snapshot.
        </div>
      )}

      <div className="card" style={{ marginBottom: 24, display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="field" style={{ flex: 1, marginBottom: 0, minWidth: 240 }}>
          <label>Git Repository Path</label>
          <input
            value={repoPath}
            onChange={(event) => setRepoPath(event.target.value)}
            placeholder="Optional: C:\\path\\to\\repo or leave empty to use the demo repo"
            onKeyDown={(event) => event.key === "Enter" && void analyze()}
          />
        </div>
        <button className="btn btn-primary" onClick={() => void analyze()} disabled={loading} style={{ flexShrink: 0 }}>
          <FolderGit2 size={16} />
          {loading ? "Analyzing Repository..." : "Analyze Repository"}
        </button>
      </div>

      {error && (
        <div
          style={{
            background: "rgba(185,28,28,0.12)",
            border: "1px solid rgba(185,28,28,0.3)",
            borderRadius: 12,
            padding: "14px 18px",
            marginBottom: 20,
            color: "#f87171",
          }}
        >
          {error}
        </div>
      )}

      {report && (
        <>
          <div className="grid-3 fade-up" style={{ marginBottom: 20 }}>
            <div className="card">
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Repository Gate</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#f1f5f9", lineHeight: 1.45, marginBottom: 8 }}>
                {gatePosture.label}
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.7 }}>
                {gatePosture.detail}
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Tracked Repository</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#f1f5f9", lineHeight: 1.45, marginBottom: 8 }}>
                {trackedRepository}
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.7 }}>
                This is the Git source currently mapped against the same student execution baseline.
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Tracking Mode</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#f1f5f9", lineHeight: 1.45, marginBottom: 8 }}>
                {trackingMode}
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.7 }}>
                Evidence is inferred by matching commit messages and changed files to the planned tasks.
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Last Evidence Snapshot</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#f1f5f9", lineHeight: 1.45, marginBottom: 8 }}>
                {lastSnapshot}
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.7 }}>
                Critical-path evidence: {criticalCovered}/{criticalIds.length || 0} gated task(s) already have commit coverage.
              </div>
            </div>
          </div>

          <div
            className="card fade-up"
            style={{
              marginBottom: 20,
              border: `1px solid ${tone.color}`,
              background: tone.bg,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
              <div style={{ maxWidth: 760 }}>
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                    borderRadius: 999,
                    padding: "6px 12px",
                    fontSize: 12,
                    fontWeight: 800,
                    color: tone.color,
                    border: `1px solid ${tone.color}`,
                    marginBottom: 14,
                  }}
                >
                  <ShieldCheck size={14} />
                  {tone.label}
                </div>
                <div style={{ fontSize: 28, fontWeight: 900, color: "#f1f5f9", marginBottom: 8 }}>
                  {evidenceCoverage}% verified repository evidence coverage
                </div>
                <div style={{ color: "#cbd5e1", fontSize: 14, lineHeight: 1.7 }}>
                  {tone.detail}
                </div>
              </div>

              <div style={{ minWidth: 240 }}>
                <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 8 }}>
                  Baseline Progress
                </div>
                <div style={{ fontSize: 30, fontWeight: 900, color: "#f8fafc", marginBottom: 12 }}>
                  {Math.round((report.overall_progress ?? 0) * 100)}%
                </div>
                <div className="progress-bar-track">
                  <div
                    className="progress-bar-fill"
                    style={{
                      width: `${(report.overall_progress ?? 0) * 100}%`,
                      background: tone.color,
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="grid-3 fade-up" style={{ marginBottom: 20 }}>
            <div className="card" style={{ borderTop: "3px solid #4ade80" }}>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                Verified Evidence
              </div>
              <div style={{ fontSize: 28, fontWeight: 900, color: "#4ade80", marginBottom: 8 }}>{highConfidenceTasks}</div>
              <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.7 }}>
                These tasks have the strongest repository proof and can be defended more confidently in front of the committee.
              </div>
            </div>

            <div className="card" style={{ borderTop: "3px solid #38bdf8" }}>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                Partial Evidence
              </div>
              <div style={{ fontSize: 28, fontWeight: 900, color: "#38bdf8", marginBottom: 8 }}>{partialEvidenceTasks}</div>
              <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.7 }}>
                These tasks have meaningful repository signals, but their completion claims should still be read with caution.
              </div>
            </div>

            <div className="card" style={{ borderTop: "3px solid #f59e0b" }}>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                Needs Review
              </div>
              <div style={{ fontSize: 28, fontWeight: 900, color: "#f59e0b", marginBottom: 8 }}>{reviewTasks}</div>
              <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.7 }}>
                These tasks were downgraded because the task ID appears in the repository, but the semantic alignment is still weak.
              </div>
            </div>
          </div>

          <div className="metric-grid fade-up fade-up-1" style={{ marginBottom: 20 }}>
            {[
              { label: "Commits Analyzed", value: report.commits_analyzed ?? 0, color: "#3b82f6" },
              { label: "Verified Tasks", value: `${verifiedTasks}/${tasks.length}`, color: "#0ea5e9" },
              { label: "Critical Path Coverage", value: `${criticalCovered}/${criticalIds.length || 0}`, color: "#f97316" },
              { label: "Needs Review", value: reviewTasks, color: "#f59e0b" },
            ].map(({ label, value, color }) => (
              <div key={label} className="metric-card" style={{ borderTop: `3px solid ${color}` }}>
                <div className="metric-value" style={{ color }}>
                  {value}
                </div>
                <div className="metric-label">{label}</div>
              </div>
            ))}
          </div>

          <div className="grid-3 fade-up fade-up-2" style={{ marginBottom: 20 }}>
            <div className="card">
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Strongest Evidence Task</div>
              <div style={{ fontSize: 13, fontWeight: 800, color: "#93c5fd", marginBottom: 6 }}>{strongestEvidenceTask?.task_id ?? "No evidence task"}</div>
              <div style={{ color: "#f1f5f9", fontSize: 14, lineHeight: 1.5, marginBottom: 8 }}>
                {strongestEvidenceTask?.task_title ?? "Repository evidence has not been mapped to any task yet."}
              </div>
              <div style={{ color: "#64748b", fontSize: 12 }}>
                {strongestEvidenceTask
                  ? `${CONFIDENCE_META[strongestEvidenceTask.evidence_confidence ?? "none"].label} · ${strongestEvidenceTask.matched_commits.length} matched commit(s) · ${Math.round((strongestEvidenceTask.completion_estimate ?? 0) * 100)}% completion estimate`
                  : "No matched commits yet"}
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Traceability Signal</div>
              <div style={{ color: "#f1f5f9", fontSize: 14, lineHeight: 1.7 }}>
                {criticalCoverage}% of the critical chain already has verified commit evidence, and the repository has recorded {totalEvidenceCommits} task-linked commit match(es) across the active baseline.
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Schedule Watch</div>
              {(report.behind_schedule ?? []).length > 0 ? (
                <div style={{ color: "#fca5a5", fontSize: 14, lineHeight: 1.7 }}>
                  {(report.behind_schedule ?? []).join(" | ")}
                </div>
              ) : (
                <div style={{ color: "#86efac", fontSize: 14, lineHeight: 1.7 }}>
                  No task is currently marked behind schedule by the monitor.
                </div>
              )}
            </div>
          </div>

          <div className="grid-2 fade-up" style={{ marginBottom: 20, gap: 18 }}>
            <div className="card">
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <Flame size={16} color="#f97316" />
                <div style={{ fontSize: 18, fontWeight: 900, color: "#f1f5f9" }}>Repository Drift Radar</div>
              </div>
              <div style={{ color: "#64748b", fontSize: 13, marginBottom: 14 }}>
                Commits listed here were found in the repository but were not mapped to any approved task with trusted evidence in the active supervisor baseline.
              </div>

              {unmatchedCommits.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {unmatchedCommits.slice(0, 6).map((commit) => (
                    <div
                      key={commit.sha}
                      style={{
                        borderRadius: 12,
                        border: "1px solid rgba(249,115,22,0.25)",
                        background: "rgba(249,115,22,0.08)",
                        padding: "12px 14px",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
                        <span style={{ color: "#fdba74", fontFamily: "monospace", fontSize: 12 }}>{commit.sha.slice(0, 7)}</span>
                        <span style={{ color: "#94a3b8", fontSize: 12 }}>{new Date(commit.date).toLocaleString()}</span>
                      </div>
                      <div style={{ color: "#f1f5f9", fontSize: 14, fontWeight: 700, lineHeight: 1.5, marginBottom: 6 }}>
                        {commit.message}
                      </div>
                      <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.6 }}>
                        {commit.files_changed?.length ? commit.files_changed.join(" | ") : "No changed-file metadata captured"}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: "#86efac", fontSize: 14, lineHeight: 1.7 }}>
                  Every analyzed commit is currently mapped to at least one approved task.
                </div>
              )}
            </div>

            <div className="card">
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <GitCommit size={16} color="#38bdf8" />
                <div style={{ fontSize: 18, fontWeight: 900, color: "#f1f5f9" }}>Repository Hotspots</div>
              </div>
              <div style={{ color: "#64748b", fontSize: 13, marginBottom: 14 }}>
                The supervisor can use this list to see which files are absorbing most of the repository activity and which planned tasks they support.
              </div>

              {repositoryHotspots.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {repositoryHotspots.map((hotspot) => (
                    <div
                      key={hotspot.path}
                      style={{
                        borderRadius: 12,
                        border: "1px solid rgba(56,189,248,0.18)",
                        background: "rgba(15,23,42,0.82)",
                        padding: "12px 14px",
                      }}
                    >
                      <div style={{ color: "#f1f5f9", fontSize: 14, fontWeight: 700, lineHeight: 1.5, marginBottom: 6 }}>
                        {hotspot.path}
                      </div>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                        <span className="badge badge-blue">{hotspot.commit_count} commit(s)</span>
                        <span className="badge badge-blue">{hotspot.linked_task_ids?.length ?? 0} linked task(s)</span>
                      </div>
                      <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.6 }}>
                        {(hotspot.linked_task_ids?.length ?? 0) > 0
                          ? `Supports: ${hotspot.linked_task_ids?.join(" | ")}`
                          : "No approved task has been linked to this file yet."}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: "#94a3b8", fontSize: 14, lineHeight: 1.7 }}>
                  File-level hotspot data will appear after the first analyzed repository snapshot with changed-file metadata.
                </div>
              )}
            </div>
          </div>

          <div className="card fade-up" style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 18, fontWeight: 900, color: "#f1f5f9", marginBottom: 6 }}>Phase Traceability</div>
            <div style={{ color: "#64748b", fontSize: 13, marginBottom: 16 }}>
              Each phase is measured against the same execution order shown in View Plan, so repository evidence can be read phase by phase rather than as raw commit noise.
            </div>
            <div className="grid-3">
              {phaseSnapshots.map((phase) => (
                <div key={phase.key} className="card" style={{ borderTop: `2px solid ${phase.toneMeta.color}` }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 10 }}>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: "#f1f5f9" }}>{phase.title}</div>
                      <div style={{ color: "#64748b", fontSize: 12, lineHeight: 1.6, marginTop: 4 }}>{phase.goal}</div>
                    </div>
                    <span
                      style={{
                        borderRadius: 999,
                        padding: "4px 10px",
                        fontSize: 11,
                        fontWeight: 800,
                        color: phase.toneMeta.color,
                        border: `1px solid ${phase.toneMeta.color}`,
                      }}
                    >
                      {phase.toneMeta.label}
                    </span>
                  </div>

                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                    <span className="badge badge-blue">{phase.evidenceTasks}/{phase.tasks.length} task(s)</span>
                    <span className="badge badge-blue">{phase.evidenceCommits} commits</span>
                    <span className="badge badge-blue">{phase.behind.length} watch item(s)</span>
                  </div>

                  {phase.behind.length > 0 ? (
                    <div style={{ fontSize: 12, color: "#fca5a5", lineHeight: 1.6 }}>
                      Behind schedule: {phase.behind.join(" | ")}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>
                      No schedule warning is currently attached to this phase.
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {verifiedTasks === 0 && (
            <div
              className="card fade-up"
              style={{
                marginBottom: 20,
                border: "1px solid rgba(249,115,22,0.35)",
                background: "rgba(249,115,22,0.08)",
              }}
            >
              <div style={{ fontSize: 16, fontWeight: 900, color: "#f8fafc", marginBottom: 8 }}>No Verified Task Tracking Yet</div>
              <div style={{ color: "#fdba74", fontSize: 13, lineHeight: 1.7 }}>
                The repository snapshot was loaded, but no commit is currently verified against the approved baseline tasks.
                To make tracking appear here, analyze the correct Git repository and use commit messages or file names that reference task IDs such as
                {" "}
                <span style={{ fontFamily: "monospace", color: "#f8fafc" }}>T001</span>
                {" / "}
                <span style={{ fontFamily: "monospace", color: "#f8fafc" }}>T002</span>.
              </div>
            </div>
          )}

          <div className="card fade-up">
            <div style={{ fontSize: 18, fontWeight: 900, color: "#f1f5f9", marginBottom: 6 }}>Task Evidence Ledger</div>
            <div style={{ color: "#64748b", fontSize: 13, marginBottom: 16 }}>
              This section shows which tasks already have repository evidence, how strong that evidence is, whether the evidence is semantically aligned, and which phase each task belongs to in the student execution baseline. Click any card to open the full commit evidence.
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {orderedEvidenceTasks.map(({ id, title, reqType, ownerRole, progress, phase }) => {
                const taskProgress = progress as TaskProgress;
                const meta = STATUS_META[taskProgress.status] ?? STATUS_META.not_started;
                const confidenceMeta = CONFIDENCE_META[taskProgress.evidence_confidence ?? "none"];
                const Icon = meta.icon;
                const pct = Math.round((taskProgress.completion_estimate ?? 0) * 100);

                return (
                  <div
                    key={id}
                    className="card"
                    style={{ borderLeft: `4px solid ${meta.color}`, cursor: "pointer" }}
                    onClick={() => setExpandedTask(expandedTask === id ? null : id)}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 14, flexWrap: "wrap", marginBottom: 10 }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                          <span style={{ fontWeight: 800, fontSize: 12, color: meta.color }}>{id}</span>
                          <span className="badge badge-blue">{phase}</span>
                          {reqType && (
                            <span className={`badge ${reqType === "NFR" ? "badge-orange" : "badge-blue"}`}>{reqType}</span>
                          )}
                          <span
                            style={{
                              borderRadius: 999,
                              padding: "4px 10px",
                              fontSize: 11,
                              fontWeight: 800,
                              color: confidenceMeta.color,
                              background: confidenceMeta.bg,
                              border: `1px solid ${confidenceMeta.color}`,
                            }}
                          >
                            {confidenceMeta.label}
                          </span>
                        </div>
                        <div style={{ fontSize: 15, color: "#f1f5f9", fontWeight: 700, lineHeight: 1.45 }}>{title}</div>
                      </div>

                      <div
                        style={{
                          background: meta.bg,
                          borderRadius: 10,
                          padding: "6px 10px",
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "flex-start",
                          gap: 4,
                          fontSize: 11,
                          color: meta.color,
                          flexShrink: 0,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <Icon size={12} /> {meta.label}
                        </div>
                        <div>{taskProgress.matched_commits.length} commit(s)</div>
                      </div>
                    </div>

                    <div className="progress-bar-track" style={{ marginBottom: 8 }}>
                      <div className="progress-bar-fill" style={{ width: `${pct}%`, background: meta.color }} />
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#64748b", flexWrap: "wrap", gap: 8 }}>
                      <span>{pct}% completion estimate</span>
                      <span>Owner lane: {ownerRole}</span>
                      <span>Alignment: {alignmentPercent(taskProgress)}%</span>
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <GitCommit size={11} />
                        {taskProgress.matched_commits.length} matched commit(s)
                      </span>
                    </div>

                    <div style={{ marginTop: 10, fontSize: 12, lineHeight: 1.6, color: confidenceMeta.color }}>
                      <span style={{ fontWeight: 800 }}>Evidence verdict:</span>
                      {" "}
                      {confidenceMeta.label}
                      {taskProgress.status === "needs_review"
                        ? ` — downgraded because repository alignment is only ${alignmentPercent(taskProgress)}%.`
                        : taskProgress.evidence_confidence === "medium"
                          ? ` — repository evidence exists, but it is not strong enough to be treated as fully verified.`
                          : taskProgress.evidence_confidence === "high"
                            ? ` — repository wording and changed files support this task strongly.`
                            : ""}
                    </div>

                    <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {(taskProgress.match_reasons ?? []).length > 0 ? (
                        (taskProgress.match_reasons ?? []).map((reason) => (
                          <span key={`${id}-inline-${reason}`} className="badge badge-blue">
                            {formatTrackingReason(reason)}
                          </span>
                        ))
                      ) : (
                        <span
                          style={{
                            borderRadius: 999,
                            padding: "4px 10px",
                            fontSize: 11,
                            fontWeight: 700,
                            color: "#94a3b8",
                            background: "rgba(100,116,139,0.15)",
                          }}
                        >
                          No repository evidence yet
                        </span>
                      )}
                    </div>

                    {!!taskProgress.evidence_note && (
                      <div
                        style={{
                          marginTop: 10,
                          borderRadius: 10,
                          padding: "10px 12px",
                          border: `1px solid ${confidenceMeta.color}`,
                          background: confidenceMeta.bg,
                          color: confidenceMeta.color,
                          fontSize: 12,
                          lineHeight: 1.6,
                        }}
                      >
                        <span style={{ fontWeight: 800 }}>Why flagged:</span>
                        {" "}
                        {taskProgress.evidence_note}
                      </div>
                    )}

                    {!!taskProgress.matched_files?.length && (
                      <div style={{ marginTop: 10, fontSize: 12, color: "#94a3b8", lineHeight: 1.6 }}>
                        <span style={{ color: "#cbd5e1", fontWeight: 700 }}>Tracked files:</span>
                        {" "}
                        {taskProgress.matched_files.slice(0, 2).join(" | ")}
                        {taskProgress.matched_files.length > 2 ? ` | +${taskProgress.matched_files.length - 2} more` : ""}
                      </div>
                    )}

                    {expandedTask === id && (
                      <div style={{ marginTop: 12, borderTop: "1px solid #1e293b", paddingTop: 12 }}>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
                          {(taskProgress.match_reasons ?? []).map((reason) => (
                            <span key={`${id}-${reason}`} className="badge badge-blue">
                              {formatTrackingReason(reason)}
                            </span>
                          ))}
                        </div>

                        <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.6, marginBottom: 10 }}>
                          Evidence confidence: <span style={{ color: confidenceMeta.color, fontWeight: 800 }}>{confidenceMeta.label}</span>
                          {" · "}
                          Alignment score: {alignmentPercent(taskProgress)}%
                        </div>

                        <div style={{ fontSize: 11, color: "#475569", marginBottom: 8 }}>Matched Commit Evidence</div>
                        {taskProgress.matched_commits.length === 0 ? (
                          <div style={{ color: "#64748b", fontSize: 12 }}>No repository evidence is currently mapped to this task.</div>
                        ) : (
                          taskProgress.matched_commits.map((sha, index) => (
                            <div key={`${id}-${sha}-${index}`} style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6, marginBottom: 6 }}>
                              <span style={{ color: "#3b82f6", fontFamily: "monospace" }}>{sha.slice(0, 7)}</span>
                              {" - "}
                              {taskProgress.evidence?.[index] ?? sha}
                            </div>
                          ))
                        )}

                        {!!taskProgress.matched_files?.length && (
                          <div style={{ marginTop: 12 }}>
                            <div style={{ fontSize: 11, color: "#475569", marginBottom: 8 }}>Touched Repository Files</div>
                            <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.7 }}>
                              {taskProgress.matched_files.join(" | ")}
                            </div>
                          </div>
                        )}

                        {(report.behind_schedule ?? []).includes(id) && (
                          <div
                            style={{
                              marginTop: 10,
                              borderRadius: 10,
                              padding: "10px 12px",
                              border: "1px solid rgba(239,68,68,0.25)",
                              background: "rgba(239,68,68,0.10)",
                              color: "#fca5a5",
                              fontSize: 12,
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                            }}
                          >
                            <AlertTriangle size={14} />
                            This task is currently flagged behind schedule by the repository monitor.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {!report && !loading && !error && (
        <div style={{ textAlign: "center", padding: "60px 20px", color: "#475569" }}>
          <GitCommit size={48} style={{ margin: "0 auto 16px", opacity: 0.4 }} />
          <p style={{ fontSize: 15 }}>Add a repository path to evaluate live commit evidence, or leave it empty to use the committee demo repository snapshot.</p>
        </div>
      )}
    </div>
  );
}
