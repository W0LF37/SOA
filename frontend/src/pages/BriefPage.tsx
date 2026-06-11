import { useEffect, useMemo, useState } from "react";
import { FolderGit2, Printer, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { getBrief, type BriefData, type MonitorReport, type RiskItem, type Task, type TeamMember } from "../lib/api";
import { DEMO_ALL_DATA, DEMO_BRIEF_DATA } from "../lib/demoProject";
import { buildExecutionRoadmap, buildPresentationTasks } from "../lib/presentation";
import { buildShowcaseData, formatQualityGate } from "../lib/projectShowcase";
import { useAppStore } from "../lib/store";

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: subtitle ? 10 : 16 }}>
        <Sparkles size={16} color="#60a5fa" />
        <div>
          <h2 className="text-lg font-bold text-white">{title}</h2>
          {subtitle ? <p className="text-sm text-gray-400 mt-1">{subtitle}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function toneFromRiskLevel(level: string | undefined) {
  const key = level?.toLowerCase();
  if (key === "critical") return { label: "Approval with elevated watch", color: "#f97316", bg: "rgba(249,115,22,0.16)" };
  if (key === "high") return { label: "Approval with active watch", color: "#f59e0b", bg: "rgba(245,158,11,0.16)" };
  if (key === "medium") return { label: "Approval with focused review", color: "#38bdf8", bg: "rgba(56,189,248,0.14)" };
  return { label: "Approval-ready posture", color: "#4ade80", bg: "rgba(74,222,128,0.14)" };
}

function severityIndex(severity: string) {
  const order = ["critical", "high", "medium", "low"];
  const index = order.indexOf(severity);
  return index === -1 ? order.length : index;
}

function shortTitle(title: string | undefined, max = 60) {
  const value = title?.trim() ?? "";
  if (value.length <= max) return value;
  return `${value.slice(0, max - 3)}...`;
}

function categoryQuestion(item: RiskItem) {
  switch (item.category) {
    case "bottleneck":
      return "Can this gate be split, parallelized, or front-loaded to reduce downstream blocking?";
    case "schedule":
      return "Does the committee accept the current effort envelope as a team roadmap rather than a solo build estimate?";
    case "dependency":
      return "Are the inferred dependencies accepted as the implementation order for review and sprint planning?";
    case "resource":
      return "Is the current owner concentration acceptable, or should backup ownership be declared?";
    case "complexity":
      return "Does this task need a narrower MVP slice before implementation starts?";
    case "integration":
      return "Are third-party assumptions and sandbox access confirmed early enough for this phase?";
    case "security":
      return "Should this control be treated as a formal release gate before committee sign-off?";
    default:
      return "Is this watch area acceptable as-is, or does it need a pre-approval action?";
  }
}

function reviewStatusValue(status: unknown) {
  if (typeof status === "string") return status;
  if (typeof status === "number") return String(status);
  return "-";
}

function repositoryBriefTone(monitor: MonitorReport | null | undefined, totalTasks: number) {
  const commits = monitor?.commits_analyzed ?? 0;
  const progress = monitor?.overall_progress ?? 0;
  const activeSignals = (monitor?.tasks_completed ?? 0) + (monitor?.tasks_in_progress ?? 0);
  const activeCoverage = totalTasks ? Math.round((activeSignals / totalTasks) * 100) : 0;

  if (commits >= 10 || progress >= 0.5) {
    return {
      label: "Repository gate active",
      detail: "The plan is not just narrative-ready; repository evidence is already active against the same execution baseline.",
      activeCoverage,
    };
  }
  if (commits >= 4 || activeSignals > 0) {
    return {
      label: "Repository gate building",
      detail: "Tracking is already attached to the baseline, but the committee should still view the evidence stream as maturing rather than complete.",
      activeCoverage,
    };
  }
  return {
    label: "Repository gate pending",
    detail: "The tracking lane exists, but stronger repository evidence is still needed before it becomes a committee-strength traceability signal.",
    activeCoverage,
  };
}

export default function BriefPage() {
  const data = useAppStore((state) => state.data);
  const [brief, setBrief] = useState<BriefData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBrief()
      .then(setBrief)
      .catch(() => setError("Live brief data is unavailable. Showing the committee demo preview instead."))
      .finally(() => setLoading(false));
  }, []);

  const displayBrief = brief ?? DEMO_BRIEF_DATA;
  const summary = data?.summary ?? DEMO_ALL_DATA.summary;
  const riskReport = data?.risks ?? DEMO_ALL_DATA.risks;
  const monitorReport = data?.monitor ?? DEMO_ALL_DATA.monitor;
  const showcase = useMemo(() => buildShowcaseData(data, displayBrief), [data, displayBrief]);
  const tasks = useMemo(
    () => buildPresentationTasks(data?.tasks?.tasks?.length ? data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? []),
    [data],
  );
  const executionRoadmap = useMemo(() => buildExecutionRoadmap(tasks), [tasks]);

  const committeeBrief = displayBrief.committee_brief ?? {};
  const effort = displayBrief.effort_summary ?? {};
  const team = (displayBrief.team_allocation ?? []).slice().sort((left, right) => right.estimated_hours - left.estimated_hours);
  const riskRegister = displayBrief.risk_register ?? [];
  const assumptions = committeeBrief.assumption_log ?? [];
  const ambiguity = committeeBrief.ambiguity_register ?? [];
  const criticalPathIds = summary?.graph_analytics?.critical_path?.task_ids ?? [];
  const taskMap = new Map(tasks.map((task) => [task.id, task]));
  const taskToPhase = new Map<string, string>();
  executionRoadmap.forEach((phase) => {
    phase.tasks.forEach((task) => {
      if (task.id) taskToPhase.set(task.id, phase.title);
    });
  });

  const generatedDate = displayBrief.generated_at
    ? new Date(displayBrief.generated_at).toLocaleDateString()
    : "Committee preview ready";
  const qualityGate = formatQualityGate(displayBrief.critic?.score ?? summary?.critic?.score);
  const posture = toneFromRiskLevel(riskReport?.risk_level);
  const repositoryGate = repositoryBriefTone(monitorReport, showcase.taskCount);
  const repositoryProgress = Math.round((monitorReport?.overall_progress ?? 0) * 100);
  const totalHours = effort.total_estimated_hours ?? tasks.reduce((sum, task) => sum + (task.estimated_hours ?? 0), 0);
  const topRole = team[0];
  const riskItems = riskReport?.risks ?? [];
  const mostExposedPhase = executionRoadmap
    .map((phase) => {
      const ids = new Set(phase.tasks.map((task) => task.id));
      const touching = riskItems.filter((item) => (item.affected_tasks ?? []).some((taskId) => ids.has(taskId)));
      return {
        phase: phase.title,
        count: touching.length,
      };
    })
    .sort((left, right) => right.count - left.count)[0];

  const releaseGateTask = useMemo(() => {
    const counts = new Map<string, { count: number; severity: number }>();
    riskItems.forEach((item) => {
      (item.affected_tasks ?? []).forEach((taskId) => {
        const current = counts.get(taskId) ?? { count: 0, severity: 99 };
        counts.set(taskId, {
          count: current.count + 1,
          severity: Math.min(current.severity, severityIndex(item.severity)),
        });
      });
    });
    return [...counts.entries()]
      .sort((left, right) => {
        if (left[1].severity !== right[1].severity) return left[1].severity - right[1].severity;
        return right[1].count - left[1].count;
      })
      .map(([taskId]) => taskMap.get(taskId))
      .find((task): task is Task => Boolean(task));
  }, [riskItems, taskMap]);

  const defensePoints = [
    {
      title: "Scope traceability",
      detail: `${showcase.taskCount} structured tasks preserve the student brief from intake and appointments through telemedicine, diagnostics, billing, portal workflows, reporting, and hardening.`,
    },
    {
      title: "Execution order",
      detail: `The implementation baseline now follows ${executionRoadmap.map((phase) => phase.title).join(" -> ")}, so the committee can defend the order as a staged delivery story rather than a raw task dump.`,
    },
    {
      title: "Dependency control",
      detail: `A ${criticalPathIds.length}-task gated chain is visible in Task Graph and Gantt, with ${riskItems.length} active watch areas already isolated for supervisor review.`,
    },
    {
      title: "Ownership readiness",
      detail: `${team.length} ownership lanes cover about ${totalHours}h of delivery work, with the heaviest execution load currently sitting in ${topRole?.role ?? "the lead delivery lane"}.`,
    },
  ];

  const committeeQuestions = useMemo(() => {
    const riskQuestions = riskItems
      .slice()
      .sort((left, right) => severityIndex(left.severity) - severityIndex(right.severity))
      .slice(0, 3)
      .map((item) => categoryQuestion(item));

    const assumptionQuestions = assumptions.slice(0, 2).map(
      (assumption) => `Does the committee accept this working assumption: ${assumption}`,
    );

    return [...riskQuestions, ...assumptionQuestions].slice(0, 4);
  }, [assumptions, riskItems]);

  const committeeApprovals = [
    `Approve the current scope baseline of ${showcase.taskCount} tasks because it already covers the full clinic and telemedicine story shown in the student workspace.`,
    `Approve the six-phase execution order because it matches the View Plan, Gantt, and Task Graph sequencing instead of repeating conflicting delivery stories.`,
    `Approve the ownership model because each major delivery lane now has a named role and effort envelope attached to it.`,
  ];

  const committeeWatchItems = [
    releaseGateTask
      ? `Protect ${releaseGateTask.id} as the primary release gate during supervisor follow-up.`
      : "Protect the primary dependency gate during supervisor follow-up.",
    mostExposedPhase?.count
      ? `Keep ${mostExposedPhase.phase} under active watch because it carries the highest concentration of current review signals.`
      : "Keep the heaviest exposed phase under active watch during supervisor review.",
    riskRegister[0]
      ? `Revisit ${riskRegister[0].risk} during execution checkpoints because it touches ${riskRegister[0].task_count} mapped task(s).`
      : "Revisit the top execution watch areas during execution checkpoints.",
  ];

  const hideReviewStatus =
    !displayBrief.admin_review
    || reviewStatusValue((displayBrief.admin_review as Record<string, unknown>).status).toLowerCase() === "empty";

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="animate-spin text-3xl mr-3">...</div>
        <span>Loading committee brief...</span>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {error ? (
        <div className="bg-blue-950/40 border border-blue-800 rounded-xl px-4 py-3 text-sm text-blue-200">
          {error}
        </div>
      ) : null}

      <div className="brief-cover-page">
        <div style={{ display: "flex", justifyContent: "center" }}>
          <Sparkles size={32} color="#0284c7" />
        </div>
        <h1 className="brief-cover-title">{showcase.title}</h1>
        <p className="brief-cover-subtitle">Committee decision pack aligned with the student baseline and supervisor review tabs</p>
        <div className="brief-cover-meta">
          <span>Generated: {generatedDate}</span>
          <span>Quality gate: {qualityGate}</span>
          <span>Review posture: {posture.label}</span>
        </div>
        <div className="brief-cover-stamp">ACADEMIC REVIEW PACK</div>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Committee Brief</h1>
          <p className="text-sm text-gray-400 mt-1">
            Final review pack for approval posture, execution defensibility, and targeted committee follow-up.
          </p>
        </div>
        <button
          onClick={() => window.print()}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: "8px 14px",
            cursor: "pointer",
            color: "#94a3b8",
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          <Printer size={14} /> Export as PDF
        </button>
      </div>

      <Section title="Committee Position" subtitle="This replaces the repeated planning summary with an approval-ready view of the same student baseline.">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-5">
          {[
            ["Recommended Decision", qualityGate === "Passed" ? "Approve for execution review" : "Approve with reservations"],
            ["Review Posture", posture.label],
            ["Primary Release Gate", releaseGateTask ? `${releaseGateTask.id}: ${shortTitle(releaseGateTask.title, 34)}` : "No gate highlighted"],
            ["Most Exposed Phase", mostExposedPhase?.phase ?? "No exposed phase"],
          ].map(([label, value]) => (
            <div key={label} className="bg-gray-700 rounded-lg p-4">
              <p className="text-xs text-gray-400 mb-1 uppercase tracking-[0.14em]">{label}</p>
              <p className="text-sm text-white font-semibold leading-relaxed">{value}</p>
            </div>
          ))}
        </div>

        <div
          style={{
            borderRadius: 12,
            padding: "14px 16px",
            border: `1px solid ${posture.color}`,
            background: posture.bg,
            color: "#e2e8f0",
            lineHeight: 1.7,
            fontSize: 14,
          }}
        >
          The committee can defend this plan as a structured clinic-and-telemedicine baseline: the student story, supervisor execution order, Gantt sequencing, task dependency review, and risk watch all now point to the same implementation narrative.
        </div>
      </Section>

      <Section title="Why This Plan Is Defensible" subtitle="Evidence pulled forward from the student workspace, View Plan, Task Graph, and Risk Indicators.">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {defensePoints.map((point) => (
            <div key={point.title} className="bg-gray-700 rounded-lg p-4">
              <div className="text-sm font-bold text-white mb-2">{point.title}</div>
              <div className="text-sm text-gray-300 leading-relaxed">{point.detail}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Repository Gate" subtitle="This is the committee-facing proof that the same approved baseline is being watched against repository evidence, not just shown in static planning tabs.">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-5">
          {[
            ["Gate Status", repositoryGate.label],
            ["Baseline Progress", `${repositoryProgress}%`],
            ["Commits Reviewed", `${monitorReport?.commits_analyzed ?? 0}`],
            ["Active Execution Signals", `${(monitorReport?.tasks_completed ?? 0) + (monitorReport?.tasks_in_progress ?? 0)}/${showcase.taskCount} tasks`],
            ["Critical Chain Under Watch", `${criticalPathIds.length} gated task(s)`],
          ].map(([label, value]) => (
            <div key={label} className="bg-gray-700 rounded-lg p-4">
              <p className="text-xs text-gray-400 mb-1 uppercase tracking-[0.14em]">{label}</p>
              <p className="text-sm text-white font-semibold leading-relaxed">{value}</p>
            </div>
          ))}
        </div>

        <div className="bg-gray-700 rounded-lg p-4 mb-5">
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <div>
              <div className="text-xs text-gray-400 uppercase tracking-[0.14em] mb-1">Repository Gate Progress</div>
              <div className="text-lg font-bold text-white">{repositoryProgress}% baseline execution visibility</div>
            </div>
            <div className="text-sm text-cyan-300 font-semibold">
              {(monitorReport?.tasks_completed ?? 0) + (monitorReport?.tasks_in_progress ?? 0)} active signal(s) across the approved plan
            </div>
          </div>
          <div className="progress-bar-track" style={{ marginBottom: 10 }}>
            <div
              className="progress-bar-fill"
              style={{
                width: `${repositoryProgress}%`,
                background: repositoryProgress >= 50 ? "#22c55e" : repositoryProgress >= 30 ? "#38bdf8" : "#f97316",
              }}
            />
          </div>
          <div className="text-xs text-gray-400 leading-relaxed">
            This progress bar is sourced from the repository monitor and reflects how much of the student-approved baseline is already showing commit-backed execution activity.
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 12,
            borderRadius: 12,
            padding: "14px 16px",
            background: "rgba(8,145,178,0.12)",
            border: "1px solid rgba(34,211,238,0.2)",
            color: "#dbeafe",
          }}
        >
          <FolderGit2 size={18} color="#38bdf8" style={{ marginTop: 2, flexShrink: 0 }} />
          <div style={{ lineHeight: 1.7, fontSize: 14 }}>
            {repositoryGate.detail} The current monitor snapshot reflects about {Math.round((monitorReport?.overall_progress ?? 0) * 100)}% baseline progress and roughly {repositoryGate.activeCoverage}% task-level execution visibility across the student plan.
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 16 }}>
          <Link
            to="/monitor"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              borderRadius: 10,
              padding: "10px 14px",
              background: "#0f172a",
              border: "1px solid rgba(56,189,248,0.35)",
              color: "#bae6fd",
              fontSize: 13,
              fontWeight: 700,
              textDecoration: "none",
            }}
          >
            <FolderGit2 size={15} />
            Open Repository Gate
          </Link>
        </div>
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Section title="Committee Can Approve Today" subtitle="Concrete decisions this tab adds beyond the student-facing narrative.">
          <div className="grid gap-3">
            {committeeApprovals.map((item) => (
              <div key={item} className="bg-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 leading-relaxed">
                {item}
              </div>
            ))}
          </div>
        </Section>

        <Section title="Committee Follow-Up Focus" subtitle="Targeted watch items distilled from the supervisor execution and risk tabs.">
          <div className="grid gap-3">
            {committeeWatchItems.map((item) => (
              <div key={item} className="bg-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 leading-relaxed">
                {item}
              </div>
            ))}
          </div>
        </Section>
      </div>

      <Section title="Execution and Ownership Snapshot" subtitle="Formal summary for effort, owners, and the core release gate defended by the current plan.">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          {[
            ["Total Hours", `${effort.total_estimated_hours ?? totalHours}h`],
            ["Working Days", `${effort.total_estimated_days ?? 0}d`],
            ["FR Hours", `${effort.fr_estimated_hours ?? 0}h`],
            ["NFR Hours", `${effort.nfr_estimated_hours ?? 0}h`],
          ].map(([label, value]) => (
            <div key={label} className="bg-gray-700 rounded-lg p-4 text-center">
              <div className="text-xl font-bold text-blue-300">{value}</div>
              <div className="text-xs text-gray-400">{label}</div>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-700">
                <th className="pb-3 pr-4">Role</th>
                <th className="pb-3 pr-4 text-center">Tasks</th>
                <th className="pb-3 pr-4 text-center">Hours</th>
                <th className="pb-3">Focus</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {team.map((member: TeamMember) => (
                <tr key={member.role} className="hover:bg-gray-700/50 transition-colors">
                  <td className="py-3 pr-4 font-medium text-white">{member.role}</td>
                  <td className="py-3 pr-4 text-center text-blue-300">{member.task_count}</td>
                  <td className="py-3 pr-4 text-center text-gray-300">{member.estimated_hours}h</td>
                  <td className="py-3 text-gray-400 text-xs">{member.focus}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Section title="Open Decisions for the Committee" subtitle="Questions worth settling during review, instead of exposing internal model traces or repeated summaries.">
          <div className="grid gap-3">
            {committeeQuestions.map((question) => (
              <div key={question} className="bg-gray-700 rounded-lg px-4 py-3 text-sm text-gray-200 leading-relaxed">
                {question}
              </div>
            ))}
          </div>
        </Section>

        <Section title="Assumptions and Ambiguities" subtitle="Only the assumptions that affect the committee conversation are surfaced here.">
          <div className="grid gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-blue-300 font-bold mb-2">Assumptions</div>
              <div className="grid gap-2">
                {assumptions.length ? assumptions.slice(0, 3).map((assumption) => (
                  <div key={assumption} className="text-sm text-gray-300 bg-gray-700 rounded-lg px-4 py-3">
                    {assumption}
                  </div>
                )) : (
                  <div className="text-sm text-gray-400 bg-gray-700 rounded-lg px-4 py-3">
                    No blocking assumptions were recorded for this plan.
                  </div>
                )}
              </div>
            </div>

            <div>
              <div className="text-xs uppercase tracking-[0.16em] text-yellow-300 font-bold mb-2">Ambiguity Register</div>
              <div className="grid gap-2">
                {ambiguity.length ? ambiguity.slice(0, 3).map((item) => (
                  <div key={`${item.task_id}-${item.original_source}`} className="bg-gray-700 rounded-lg p-4">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-xs font-mono text-yellow-300">{item.task_id}</span>
                      <span className="text-xs text-gray-500">{item.original_source}</span>
                    </div>
                    <div className="text-sm text-gray-300">{item.reason}</div>
                  </div>
                )) : (
                  <div className="text-sm text-gray-400 bg-gray-700 rounded-lg px-4 py-3">
                    The current student brief is specific enough that no ambiguity item is blocking execution readiness.
                  </div>
                )}
              </div>
            </div>
          </div>
        </Section>
      </div>

      <Section title="Condensed Risk Register" subtitle="Short committee-facing risk themes, not a duplicate of the full supervisor risk console.">
        <div className="grid gap-3">
          {riskRegister.map((item) => {
            const mappedTitles = item.task_ids
              .map((taskId) => taskMap.get(taskId))
              .filter((task): task is Task => Boolean(task))
              .slice(0, 3)
              .map((task) => `${task.id}: ${shortTitle(task.title, 38)}`);

            return (
              <div key={item.risk} className="bg-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <p className="text-sm text-white font-medium">{item.risk}</p>
                  <span className="text-xs bg-red-900 text-red-300 px-2 py-0.5 rounded-full">
                    {item.task_count} tasks
                  </span>
                </div>
                <p className="text-xs text-gray-400 leading-relaxed">
                  {mappedTitles.length ? mappedTitles.join(" | ") : item.task_ids.join(", ")}
                </p>
              </div>
            );
          })}
        </div>
      </Section>

      {!hideReviewStatus && displayBrief.admin_review ? (
        <Section title="Supervisor Review Status" subtitle="Shown only when the review queue contains a real decision state worth documenting in the committee pack.">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
            {["status", "approved", "edited", "rejected", "skipped"].map((key) => (
              <div key={key} className="bg-gray-700 rounded-lg p-3">
                <div className="text-lg font-bold text-white capitalize">
                  {reviewStatusValue((displayBrief.admin_review as Record<string, unknown>)?.[key])}
                </div>
                <div className="text-xs text-gray-400 capitalize">{key}</div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <div
        style={{
          borderRadius: 16,
          padding: "18px 20px",
          background: "rgba(15,23,42,0.92)",
          border: "1px solid rgba(74,222,128,0.18)",
          color: "#d1fae5",
          display: "flex",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <ShieldCheck size={20} color="#4ade80" style={{ marginTop: 2, flexShrink: 0 }} />
        <div style={{ lineHeight: 1.7 }}>
          This brief is export-ready because it no longer repeats the student summary, does not expose internal fallback traces, and translates the same baseline into a committee decision view with approvals, watch items, and open review questions.
        </div>
      </div>
    </div>
  );
}
