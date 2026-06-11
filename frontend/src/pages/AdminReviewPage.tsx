import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";

import {
  getAdminQueue,
  submitReview,
  type AdminQueueItem,
  type ReviewDecision,
  type ReviewResult,
  type RiskItem,
  type Task,
} from "../lib/api";
import { DEMO_ALL_DATA } from "../lib/demoProject";
import { buildExecutionRoadmap, buildPresentationTasks } from "../lib/presentation";
import { useAppStore } from "../lib/store";

type DecisionState = {
  action: ReviewDecision["action"];
  new_title: string;
  note?: string;
};

const ACTION_STYLES: Record<ReviewDecision["action"], string> = {
  approved: "bg-green-600 hover:bg-green-700 text-white",
  edited: "bg-yellow-500 hover:bg-yellow-600 text-white",
  rejected: "bg-red-600 hover:bg-red-700 text-white",
  skipped: "bg-gray-500 hover:bg-gray-600 text-white",
};

const COMPLEXITY_BADGE: Record<number, string> = {
  1: "bg-green-900 text-green-300",
  2: "bg-blue-900 text-blue-300",
  3: "bg-yellow-900 text-yellow-300",
  4: "bg-orange-900 text-orange-300",
  5: "bg-red-900 text-red-300",
};

function severityIndex(severity: string) {
  const order = ["critical", "high", "medium", "low"];
  const index = order.indexOf(severity);
  return index === -1 ? order.length : index;
}

function shortText(value: string | undefined, max = 60) {
  const text = value?.trim() ?? "";
  if (text.length <= max) return text;
  return `${text.slice(0, max - 3)}...`;
}

function buildReleaseGate(tasks: Task[], risks: RiskItem[]) {
  const taskMap = new Map(tasks.map((task) => [task.id, task]));
  const scores = new Map<string, { count: number; severity: number }>();

  risks.forEach((item) => {
    (item.affected_tasks ?? []).forEach((taskId) => {
      const current = scores.get(taskId) ?? { count: 0, severity: 99 };
      scores.set(taskId, {
        count: current.count + 1,
        severity: Math.min(current.severity, severityIndex(item.severity)),
      });
    });
  });

  return [...scores.entries()]
    .sort((left, right) => {
      if (left[1].severity !== right[1].severity) return left[1].severity - right[1].severity;
      return right[1].count - left[1].count;
    })
    .map(([taskId]) => taskMap.get(taskId))
    .find((task): task is Task => Boolean(task));
}

function buildReviewAsk(task: Task, criticalIds: Set<string>, riskItems: RiskItem[]) {
  const touches = riskItems.filter((item) => (item.affected_tasks ?? []).includes(task.id));
  if (criticalIds.has(task.id ?? "")) {
    return "Confirm that this release-gating dependency should remain on the critical path as planned.";
  }
  if ((task.estimated_hours ?? 0) >= 35) {
    return "Confirm that the current effort envelope is acceptable or split this task into a narrower MVP slice.";
  }
  if (touches.some((item) => item.category === "security" || item.category === "bottleneck")) {
    return "Confirm that the current mitigation is sufficient before downstream phases depend on this task.";
  }
  return "Confirm that this task can move forward without extra supervisor intervention.";
}

function buildReviewReason(task: Task, criticalIds: Set<string>, riskItems: RiskItem[]) {
  const touches = riskItems.filter((item) => (item.affected_tasks ?? []).includes(task.id));
  if (criticalIds.has(task.id ?? "")) return "Release-gating dependency";
  if ((task.estimated_hours ?? 0) >= 35) return "Heavy effort concentration";
  if (touches.length) return "Risk-linked checkpoint";
  return "Supervisor visibility checkpoint";
}

function ChecklistCard({
  title,
  status,
  detail,
}: {
  title: string;
  status: string;
  detail: string;
}) {
  const tone =
    status === "Ready"
      ? { color: "#4ade80", bg: "rgba(74,222,128,0.14)" }
      : status === "Watch"
        ? { color: "#f97316", bg: "rgba(249,115,22,0.14)" }
        : { color: "#38bdf8", bg: "rgba(56,189,248,0.12)" };

  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="text-sm font-bold text-white">{title}</div>
        <span
          style={{
            borderRadius: 999,
            padding: "4px 10px",
            fontSize: 11,
            fontWeight: 900,
            color: tone.color,
            background: tone.bg,
            border: `1px solid ${tone.color}`,
          }}
        >
          {status}
        </span>
      </div>
      <div className="text-sm text-gray-300 leading-relaxed">{detail}</div>
    </div>
  );
}

function ReviewCandidateCard({
  task,
  phase,
  reason,
  ask,
}: {
  task: Task;
  phase: string;
  reason: string;
  ask: string;
}) {
  return (
    <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-mono text-blue-300">{task.id}</span>
          <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">{task.req_type}</span>
          <span className={`text-xs px-2 py-0.5 rounded ${COMPLEXITY_BADGE[task.complexity] || "bg-gray-700 text-gray-300"}`}>
            C{task.complexity}
          </span>
          <span className="text-xs bg-gray-700 text-sky-300 px-2 py-0.5 rounded">{phase}</span>
        </div>
        <span className="text-xs bg-orange-950 text-orange-300 px-2 py-1 rounded-full">{reason}</span>
      </div>
      <div className="text-base font-semibold text-white mb-2">{task.title}</div>
      <div className="text-sm text-gray-400 mb-3">
        Owner: {task.suggested_owner_role ?? "Supervisor review"} · {task.estimated_hours ?? 0}h
      </div>
      <div className="text-sm text-gray-300 leading-relaxed">{ask}</div>
    </div>
  );
}

function EmptyWorkspace({
  status,
}: {
  status: string;
}) {
  const navigate = useNavigate();
  const data = useAppStore((s) => s.data);

  const tasks = useMemo(
    () => buildPresentationTasks(data?.tasks?.tasks?.length ? data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? []),
    [data],
  );
  const summary = data?.summary ?? DEMO_ALL_DATA.summary;
  const risks = data?.risks ?? DEMO_ALL_DATA.risks;
  const executionRoadmap = useMemo(() => buildExecutionRoadmap(tasks), [tasks]);
  const criticalIds = new Set<string>(summary?.graph_analytics?.critical_path?.task_ids ?? []);
  const riskItems = risks?.risks ?? [];

  const taskToPhase = new Map<string, string>();
  executionRoadmap.forEach((phase) => {
    phase.tasks.forEach((task) => {
      if (task.id) taskToPhase.set(task.id, phase.title);
    });
  });

  const releaseGate = buildReleaseGate(tasks, riskItems);
  const mostExposedPhase = executionRoadmap
    .map((phase) => {
      const ids = new Set(phase.tasks.map((task) => task.id));
      return {
        title: phase.title,
        count: riskItems.filter((item) => (item.affected_tasks ?? []).some((taskId) => ids.has(taskId))).length,
      };
    })
    .sort((left, right) => right.count - left.count)[0];

  const topOwner = [...(summary?.team_allocation ?? DEMO_ALL_DATA.summary?.team_allocation ?? [])]
    .sort((left, right) => (right.estimated_hours ?? 0) - (left.estimated_hours ?? 0))[0];

  const reviewCandidates = useMemo(() => {
    const candidateIds = new Set<string>();

    (summary?.graph_analytics?.critical_path?.task_ids ?? []).forEach((taskId) => candidateIds.add(taskId));

    riskItems
      .slice()
      .sort((left, right) => severityIndex(left.severity) - severityIndex(right.severity))
      .forEach((item) => {
        (item.affected_tasks ?? []).slice(0, 2).forEach((taskId) => candidateIds.add(taskId));
      });

    tasks
      .slice()
      .sort((left, right) => (right.estimated_hours ?? 0) - (left.estimated_hours ?? 0))
      .slice(0, 2)
      .forEach((task) => {
        if (task.id) candidateIds.add(task.id);
      });

    return [...candidateIds]
      .map((taskId) => tasks.find((task) => task.id === taskId))
      .filter((task): task is Task => Boolean(task))
      .slice(0, 5);
  }, [riskItems, summary, tasks]);

  const signOffChecklist = [
    {
      title: "Scope alignment with the student brief",
      status: "Ready",
      detail: "The execution baseline still covers the full clinic and telemedicine journey from intake and appointments through diagnostics, billing, portal workflows, reporting, and hardening.",
    },
    {
      title: "Execution order consistency",
      status: "Ready",
      detail: `View Plan, Gantt, Task Graph, and Committee Brief now follow the same six-phase delivery story instead of conflicting sequences.`,
    },
    {
      title: "Release-gate acceptance",
      status: releaseGate ? "Review" : "Ready",
      detail: releaseGate
        ? `${releaseGate.id} is currently the strongest candidate for a supervisor sign-off gate before the student baseline can safely move downstream.`
        : "No single release gate currently dominates the baseline review.",
    },
    {
      title: "Risk follow-up posture",
      status: riskItems.length > 0 ? "Watch" : "Ready",
      detail: riskItems.length > 0
        ? `${riskItems.length} active watch area(s) are already isolated in Risk Indicators, so the supervisor only needs to confirm whether the mitigations are accepted before approval.`
        : "No active watch area currently requires additional supervisor follow-up.",
    },
  ];

  return (
    <div className="p-6 space-y-6">
      <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div style={{ maxWidth: 760 }}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                background: "rgba(59,130,246,0.12)",
                color: "#7dd3fc",
                border: "1px solid rgba(59,130,246,0.28)",
                borderRadius: 999,
                padding: "6px 12px",
                fontSize: 12,
                fontWeight: 800,
                marginBottom: 14,
              }}
            >
              <ClipboardCheck size={14} />
              Supervisor Sign-Off Workspace
            </div>
            <h1 className="text-2xl font-bold text-white mb-3">No manual review queue is active, so this page switches to approval review.</h1>
            <p className="text-sm text-gray-300 leading-relaxed">
              The API did not flag task titles for edit, but the supervisor still needs a place to confirm release gates,
              execution order, risk acceptance, and the final go/no-go path before approving the student plan.
            </p>
          </div>

          <div className="grid gap-3 min-w-[280px] flex-1">
            <div className="bg-gray-900/70 rounded-lg p-4 border border-gray-700">
              <div className="text-xs uppercase tracking-[0.14em] text-gray-400 mb-2">Queue Status</div>
              <div className="text-lg font-bold text-white capitalize">{status === "no_pipeline_run" ? "No pipeline review queue" : "Auto-approved queue state"}</div>
            </div>
            <div className="bg-gray-900/70 rounded-lg p-4 border border-gray-700">
              <div className="text-xs uppercase tracking-[0.14em] text-gray-400 mb-2">Primary Release Gate</div>
              <div className="text-sm font-semibold text-white">{releaseGate ? `${releaseGate.id}: ${shortText(releaseGate.title, 42)}` : "No gate task highlighted"}</div>
            </div>
            <div className="bg-gray-900/70 rounded-lg p-4 border border-gray-700">
              <div className="text-xs uppercase tracking-[0.14em] text-gray-400 mb-2">Most Exposed Phase</div>
              <div className="text-sm font-semibold text-white">{mostExposedPhase?.title ?? "No exposed phase"}</div>
            </div>
            <div className="bg-gray-900/70 rounded-lg p-4 border border-gray-700">
              <div className="text-xs uppercase tracking-[0.14em] text-gray-400 mb-2">Heaviest Owner Lane</div>
              <div className="text-sm font-semibold text-white">{topOwner ? `${topOwner.role} · ${topOwner.estimated_hours}h` : "No owner lane mapped"}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center gap-3 mb-4">
          <CheckCircle2 size={18} color="#60a5fa" />
          <h2 className="text-lg font-bold text-white">Supervisor Sign-Off Checklist</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {signOffChecklist.map((item) => (
            <ChecklistCard
              key={item.title}
              title={item.title}
              status={item.status}
              detail={item.detail}
            />
          ))}
        </div>
      </section>

      <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center gap-3 mb-4">
          <ShieldCheck size={18} color="#60a5fa" />
          <h2 className="text-lg font-bold text-white">Priority Review Candidates</h2>
        </div>
        <p className="text-sm text-gray-400 mb-4">
          These items were selected from the same student baseline using critical-path position, risk touchpoints, and effort concentration. They are not title-edit queue items; they are approval checkpoints.
        </p>
        <div className="grid gap-4">
          {reviewCandidates.map((task) => (
            <ReviewCandidateCard
              key={task.id}
              task={task}
              phase={taskToPhase.get(task.id) ?? "Cross-plan checkpoint"}
              reason={buildReviewReason(task, criticalIds, riskItems)}
              ask={buildReviewAsk(task, criticalIds, riskItems)}
            />
          ))}
        </div>
      </section>

      <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <div className="flex items-center gap-3 mb-4">
          <ArrowRight size={18} color="#60a5fa" />
          <h2 className="text-lg font-bold text-white">Decision Route</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
          {[
            {
              title: "1. Inspect execution risk",
              detail: "Use Risk Indicators to confirm whether the active watch areas are acceptable or need explicit mitigation before sign-off.",
            },
            {
              title: "2. Read the committee decision pack",
              detail: "Use Committee Brief when you want the export-ready explanation of why this plan is defensible and what the committee can approve today.",
            },
            {
              title: "3. Approve or reject in Communication",
              detail: "Use Communication as the final decision channel to send approval, rejection, or a decision comment back to the student.",
            },
          ].map((step) => (
            <div key={step.title} className="bg-gray-900/70 rounded-lg p-4 border border-gray-700">
              <div className="text-sm font-bold text-white mb-2">{step.title}</div>
              <div className="text-sm text-gray-300 leading-relaxed">{step.detail}</div>
            </div>
          ))}
        </div>

        <div className="flex gap-3 flex-wrap">
          <button
            onClick={() => navigate("/risks")}
            style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: "10px 14px", color: "#cbd5e1", fontSize: 13, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
          >
            <ShieldCheck size={14} /> Open Risk Indicators
          </button>
          <button
            onClick={() => navigate("/brief")}
            style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: "10px 14px", color: "#cbd5e1", fontSize: 13, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
          >
            <FileText size={14} /> Open Committee Brief
          </button>
          <button
            onClick={() => navigate("/chat")}
            style={{ background: "#0284c7", border: "1px solid #0ea5e9", borderRadius: 8, padding: "10px 14px", color: "#ffffff", fontSize: 13, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
          >
            <MessageSquare size={14} /> Go to Communication
          </button>
        </div>
      </section>
    </div>
  );
}

export default function AdminReviewPage() {
  const [items, setItems] = useState<AdminQueueItem[]>([]);
  const [status, setStatus] = useState<string>("loading");
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({});
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminQueue()
      .then((q) => {
        setItems(q.items);
        setStatus(q.status);
        const initial: Record<string, DecisionState> = {};
        q.items.forEach((item) => {
          initial[item.task_id] = { action: "skipped", new_title: item.title, note: "" };
        });
        setDecisions(initial);
      })
      .catch(() => setStatus("error"));
  }, []);

  const setAction = (taskId: string, action: ReviewDecision["action"]) => {
    setDecisions((prev) => ({ ...prev, [taskId]: { ...prev[taskId], action } }));
  };

  const setTitle = (taskId: string, new_title: string) => {
    setDecisions((prev) => ({ ...prev, [taskId]: { ...prev[taskId], new_title } }));
  };

  const setNote = (taskId: string, note: string) => {
    setDecisions((prev) => ({ ...prev, [taskId]: { ...prev[taskId], note } }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload: ReviewDecision[] = Object.entries(decisions).map(([task_id, d]) => ({
        task_id,
        action: d.action,
        new_title: d.action === "edited" ? d.new_title : undefined,
        note: d.note?.trim() ? d.note.trim() : undefined,
      }));
      const res = await submitReview(payload);
      setResult(res);
    } catch {
      setError("Failed to submit review. Make sure the API is running.");
    } finally {
      setSubmitting(false);
    }
  };

  const decided = Object.values(decisions).filter((d) => d.action !== "skipped").length;
  const total = items.length;

  if (status === "no_pipeline_run" || status === "empty" || (status === "reviewed" && total === 0)) {
    return <EmptyWorkspace status={status} />;
  }

  if (status === "error") {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-red-400">
        <p className="text-lg">Could not load review queue. Is the API running?</p>
      </div>
    );
  }

  if (result) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <div className="bg-gray-800 rounded-xl p-8 text-center border border-green-700">
          <div className="text-5xl mb-4">OK</div>
          <h2 className="text-2xl font-bold text-white mb-2">Review Submitted</h2>
          <p className="text-gray-400 mb-6">
            {result.kept_tasks} tasks kept · {result.rejected_tasks} rejected
          </p>
          <div className="grid grid-cols-4 gap-4 text-center">
            {Object.entries(result.counts).map(([action, count]) => (
              <div key={action} className="bg-gray-700 rounded-lg p-3">
                <div className="text-2xl font-bold text-white">{count}</div>
                <div className="text-xs text-gray-400 capitalize">{action}</div>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-500 mt-4">
            Final tasks saved to <code className="text-green-400">data/processed/tasks_final.json</code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-2xl font-bold text-white">Supervisor Review</h1>
          <p className="text-gray-400 text-sm mt-1">
            {total} task{total !== 1 ? "s" : ""} flagged for manual review
          </p>
          <p className="text-gray-500 text-xs mt-1">
            data/processed/tasks_final.json is created after submitting these decisions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const updated: Record<string, DecisionState> = {};
              items.forEach((item) => {
                if (!decisions[item.task_id] || decisions[item.task_id].action === "skipped") {
                  updated[item.task_id] = {
                    action: "approved",
                    new_title: decisions[item.task_id]?.new_title ?? item.title,
                    note: decisions[item.task_id]?.note ?? "",
                  };
                }
              });
              setDecisions((prev) => ({ ...prev, ...updated }));
            }}
            style={{ background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 8, padding: "8px 14px", color: "#4ade80", fontSize: 12, cursor: "pointer" }}
          >
            Approve All
          </button>
          {status === "reviewed" && (
            <span className="text-xs bg-blue-900 text-blue-300 px-3 py-1 rounded-full">
              Previously reviewed
            </span>
          )}
        </div>
      </div>

      <div className="bg-gray-700 rounded-full h-2 mb-4">
        <div
          className="bg-blue-500 h-2 rounded-full transition-all"
          style={{ width: `${total > 0 ? (decided / total) * 100 : 0}%` }}
        />
      </div>
      <p className="text-xs text-gray-400 mb-4">
        {decided} / {total} decisions made
      </p>

      <div className="space-y-4">
        {items.map((item) => {
          const d = decisions[item.task_id] || { action: "skipped", new_title: item.title, note: "" };
          return (
            <div
              key={item.task_id}
              className={`bg-gray-800 rounded-xl p-5 border transition-all ${
                d.action === "approved"
                  ? "border-green-700"
                  : d.action === "rejected"
                    ? "border-red-800"
                    : d.action === "edited"
                      ? "border-yellow-700"
                      : "border-gray-700"
              }`}
            >
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-xs font-mono text-gray-500">{item.task_id}</span>
                    <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">
                      {item.req_type}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${COMPLEXITY_BADGE[item.complexity] || "bg-gray-700 text-gray-300"}`}
                    >
                      C{item.complexity}
                    </span>
                    <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">
                      {item.source}
                    </span>
                    {item.optional && (
                      <span className="text-xs bg-purple-900 text-purple-300 px-2 py-0.5 rounded">
                        optional
                      </span>
                    )}
                  </div>
                  <h3 className="font-semibold text-white text-base">{item.title}</h3>
                  {item.reason && (
                    <p className="text-xs text-yellow-400 mt-1">Flag: {item.reason}</p>
                  )}
                  {item.description && (
                    <p className="text-sm text-gray-400 mt-1 line-clamp-2">{item.description}</p>
                  )}
                </div>

                <div className="flex gap-2 flex-shrink-0 flex-wrap">
                  {(["approved", "edited", "rejected", "skipped"] as const).map((action) => (
                    <button
                      key={action}
                      onClick={() => setAction(item.task_id, action)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all border ${
                        d.action === action
                          ? `${ACTION_STYLES[action]} ring-2 ring-offset-1 ring-offset-gray-800 ring-current`
                          : "bg-gray-700 text-gray-400 border-gray-600 hover:bg-gray-600"
                      }`}
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>

              {d.action === "edited" && (
                <div className="mt-3">
                  <input
                    type="text"
                    value={d.new_title}
                    onChange={(e) => setTitle(item.task_id, e.target.value)}
                    placeholder="New task title..."
                    className="w-full bg-gray-700 border border-yellow-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                  />
                </div>
              )}

              {(d.action === "edited" || d.action === "rejected") && (
                <textarea
                  placeholder="Add a note for this decision (optional)..."
                  value={d.note ?? ""}
                  onChange={(e) => setNote(item.task_id, e.target.value)}
                  rows={2}
                  style={{ width: "100%", marginTop: 8, background: "#020617", border: "1px solid #334155", borderRadius: 8, color: "#f8fafc", padding: "8px 10px", fontSize: 12, resize: "none" }}
                />
              )}
            </div>
          );
        })}
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end pt-4">
        <button
          onClick={handleSubmit}
          disabled={submitting || total === 0}
          className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl font-semibold text-sm transition-all"
        >
          {submitting ? "Submitting..." : `Submit All Decisions (${total})`}
        </button>
      </div>
    </div>
  );
}
