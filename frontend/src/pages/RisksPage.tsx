import { useMemo, useState } from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";

import type { RiskItem, RiskReport, Task } from "../lib/api";
import { DEMO_ALL_DATA } from "../lib/demoProject";
import {
  buildExecutionRoadmap,
  buildPresentationTasks,
  type ExecutionRoadmapPhase,
} from "../lib/presentation";
import { useAppStore } from "../lib/store";

const CATEGORY_LABELS: Record<string, string> = {
  bottleneck: "Dependency bottleneck",
  schedule: "Schedule pressure",
  dependency: "Dependency chain risk",
  resource: "Ownership concentration",
  complexity: "Complexity spike",
  quality: "Quality signal",
  integration: "Integration coordination",
  security: "Security hardening",
};

const CATEGORY_NOTES: Record<string, string> = {
  bottleneck: "This watch area can delay multiple downstream milestones in the student delivery plan.",
  schedule: "This watch area affects how comfortably the student plan can reach the committee-ready baseline on time.",
  dependency: "This watch area affects how reliably one execution phase can hand off to the next.",
  resource: "This watch area concentrates execution knowledge in a narrow ownership lane and needs closer supervision.",
  complexity: "This watch area adds review effort and uncertainty inside one delivery slice.",
  quality: "This watch area can reduce confidence in the committee-facing output if left unmanaged.",
  integration: "This watch area sits on boundaries between the core clinic workflows and external service dependencies.",
  security: "This watch area matters because the student plan includes clinical and payment-sensitive workflows.",
};

const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;

const SEVERITY_META: Record<string, { color: string; icon: string; label: string; watchLabel: string }> = {
  critical: { color: "#ef4444", icon: "P1", label: "Critical", watchLabel: "Immediate Watch" },
  high: { color: "#f97316", icon: "P2", label: "High", watchLabel: "Active Watch" },
  medium: { color: "#eab308", icon: "P3", label: "Medium", watchLabel: "Review Watch" },
  low: { color: "#4ade80", icon: "P4", label: "Low", watchLabel: "Monitored" },
};

const EMPTY_RISK_REPORT: RiskReport = {
  risk_level: "low",
  risk_score: 0,
  total_risks: 0,
  risks: [],
  mitigations: [],
  generated_at: "",
};

type PhaseExposure = {
  phase: ExecutionRoadmapPhase;
  riskCount: number;
  impactedTasks: Task[];
  impactedHours: number;
  topSeverity: (typeof SEVERITY_ORDER)[number];
};

function riskTone(level: string) {
  const key = level.toLowerCase();
  if (key === "critical") return { color: "#f97316", bg: "rgba(249,115,22,0.14)", label: "Elevated watch posture" };
  if (key === "high") return { color: "#f59e0b", bg: "rgba(245,158,11,0.14)", label: "Active watch posture" };
  if (key === "medium") return { color: "#38bdf8", bg: "rgba(56,189,248,0.12)", label: "Focused review posture" };
  return { color: "#4ade80", bg: "rgba(74,222,128,0.12)", label: "Stable watch posture" };
}

function categoryLabel(category: string | undefined) {
  if (!category) return "Risk indicator";
  return CATEGORY_LABELS[category] ?? category;
}

function categoryNote(category: string | undefined) {
  if (!category) return "This watch area should be reviewed against the student delivery baseline.";
  return CATEGORY_NOTES[category] ?? "This watch area should be reviewed against the student delivery baseline.";
}

function severityIndex(severity: string) {
  const index = SEVERITY_ORDER.indexOf(severity as (typeof SEVERITY_ORDER)[number]);
  return index === -1 ? SEVERITY_ORDER.length : index;
}

function formatTitle(title: string | undefined, max = 46) {
  const value = title?.trim() ?? "";
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}...`;
}

function unique<T>(items: T[]) {
  return [...new Set(items)];
}

export default function RisksPage() {
  const data = useAppStore((state) => state.data);
  const risk = data?.risks ?? DEMO_ALL_DATA.risks ?? EMPTY_RISK_REPORT;
  const summary = data?.summary ?? DEMO_ALL_DATA.summary;
  const usingDemo = !data?.risks;
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    critical: true,
    high: true,
    medium: true,
    low: false,
  });

  const tasks = useMemo(
    () => buildPresentationTasks(data?.tasks?.tasks?.length ? data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? []),
    [data],
  );

  const executionRoadmap = useMemo(() => buildExecutionRoadmap(tasks), [tasks]);
  const taskMap = useMemo(() => new Map(tasks.map((task) => [task.id, task])), [tasks]);
  const taskToPhase = useMemo(() => {
    const map = new Map<string, ExecutionRoadmapPhase>();
    executionRoadmap.forEach((phase) => {
      phase.tasks.forEach((task) => {
        if (task.id) map.set(task.id, phase);
      });
    });
    return map;
  }, [executionRoadmap]);

  const risks = risk.risks ?? [];
  const tone = riskTone(risk.risk_level ?? "low");
  const grouped = SEVERITY_ORDER.reduce((acc, severity) => {
    acc[severity] = risks.filter((item) => item.severity === severity);
    return acc;
  }, {} as Record<(typeof SEVERITY_ORDER)[number], RiskItem[]>);

  const affectedTaskIds = unique(risks.flatMap((item) => item.affected_tasks ?? []));
  const affectedTasks = affectedTaskIds.map((taskId) => taskMap.get(taskId)).filter((task): task is Task => Boolean(task));
  const affectedHours = affectedTasks.reduce((sum, task) => sum + (task.estimated_hours ?? 0), 0);

  const phaseExposure = useMemo<PhaseExposure[]>(() => {
    return executionRoadmap.map((phase) => {
      const phaseTaskIds = new Set(phase.tasks.map((task) => task.id));
      const phaseRisks = risks.filter((item) => (item.affected_tasks ?? []).some((taskId) => phaseTaskIds.has(taskId)));
      const impactedTasks = phase.tasks.filter((task) => phaseRisks.some((item) => (item.affected_tasks ?? []).includes(task.id)));
      const topSeverity = phaseRisks.length
        ? [...phaseRisks].sort((left, right) => severityIndex(left.severity) - severityIndex(right.severity))[0].severity
        : "low";

      return {
        phase,
        riskCount: phaseRisks.length,
        impactedTasks,
        impactedHours: impactedTasks.reduce((sum, task) => sum + (task.estimated_hours ?? 0), 0),
        topSeverity: topSeverity as (typeof SEVERITY_ORDER)[number],
      };
    });
  }, [executionRoadmap, risks]);

  const mostExposedPhase = [...phaseExposure]
    .sort((left, right) => {
      if (right.riskCount !== left.riskCount) return right.riskCount - left.riskCount;
      return right.impactedHours - left.impactedHours;
    })[0];

  const gateTask = useMemo(() => {
    const scores = new Map<string, { count: number; severityRank: number }>();
    risks.forEach((item) => {
      (item.affected_tasks ?? []).forEach((taskId) => {
        const current = scores.get(taskId) ?? { count: 0, severityRank: SEVERITY_ORDER.length };
        scores.set(taskId, {
          count: current.count + 1,
          severityRank: Math.min(current.severityRank, severityIndex(item.severity)),
        });
      });
    });

    return [...scores.entries()]
      .sort((left, right) => {
        if (left[1].severityRank !== right[1].severityRank) return left[1].severityRank - right[1].severityRank;
        return right[1].count - left[1].count;
      })
      .map(([taskId]) => taskMap.get(taskId))
      .find((task): task is Task => Boolean(task));
  }, [risks, taskMap]);

  const projectName =
    ((summary?.plan_highlights as { project_name?: string } | undefined)?.project_name)
    ?? "Smart Clinic & Telemedicine Platform";

  return (
    <div className="fade-up">
      <h1 className="page-title">
        <AlertTriangle size={22} /> Risk Indicators
      </h1>
      <p className="page-sub">Supervisor watch review linked to the same student delivery baseline shown in the planning workspace</p>

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
          Live risk output is unavailable, so this page is showing the committee demo risk review derived from the same student plan baseline.
        </div>
      )}

      <section
        style={{
          background: "rgba(15,23,42,0.92)",
          border: "1px solid #1e293b",
          borderRadius: 18,
          padding: 22,
          marginBottom: 18,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 18, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div style={{ maxWidth: 720 }}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                borderRadius: 999,
                padding: "8px 14px",
                background: tone.bg,
                color: tone.color,
                border: `1px solid ${tone.color}`,
                fontSize: 13,
                fontWeight: 900,
                marginBottom: 12,
              }}
            >
              {tone.label}
            </div>
            <div style={{ fontSize: 28, fontWeight: 900, color: "#f8fafc", marginBottom: 10 }}>
              {projectName}
            </div>
            <div style={{ fontSize: 14, lineHeight: 1.65, color: "#cbd5e1" }}>
              This page focuses on where the student plan needs supervisor attention, which phase carries the heaviest delivery exposure, and which release gates should be defended during committee review.
            </div>
          </div>

          <div style={{ display: "grid", gap: 10, minWidth: 280, flex: "1 1 320px" }}>
            <div style={{ borderRadius: 14, padding: "14px 16px", background: "rgba(8,13,26,0.72)", border: "1px solid #1e293b" }}>
              <div style={{ color: "#64748b", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                Active watch areas
              </div>
              <div style={{ fontSize: 26, fontWeight: 900, color: "#f8fafc" }}>{risks.length}</div>
            </div>
            <div style={{ borderRadius: 14, padding: "14px 16px", background: "rgba(8,13,26,0.72)", border: "1px solid #1e293b" }}>
              <div style={{ color: "#64748b", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                Most exposed phase
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: "#f8fafc" }}>{mostExposedPhase?.phase.title ?? "No active watch area"}</div>
            </div>
            <div style={{ borderRadius: 14, padding: "14px 16px", background: "rgba(8,13,26,0.72)", border: "1px solid #1e293b" }}>
              <div style={{ color: "#64748b", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                Primary release gate
              </div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc" }}>
                {gateTask ? `${gateTask.id}: ${gateTask.title}` : "No gate task identified"}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        style={{
          background: "rgba(15,23,42,0.92)",
          border: "1px solid #1e293b",
          borderRadius: 18,
          padding: 22,
          marginBottom: 18,
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "#38bdf8", textTransform: "uppercase", marginBottom: 10 }}>
          Phase Exposure Review
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          {phaseExposure.map((item) => {
            const severity = SEVERITY_META[item.topSeverity];
            const phaseColor = item.riskCount > 0 ? severity.color : "#38bdf8";
            return (
              <div
                key={item.phase.key}
                style={{
                  borderRadius: 16,
                  padding: "16px",
                  border: `1px solid ${phaseColor}55`,
                  background: "rgba(8,13,26,0.72)",
                }}
              >
                <div style={{ fontSize: 17, fontWeight: 800, color: "#f8fafc", marginBottom: 8 }}>
                  {item.phase.title}
                </div>
                <div style={{ fontSize: 12, lineHeight: 1.55, color: "#94a3b8", marginBottom: 10 }}>
                  {item.riskCount > 0
                    ? `${item.riskCount} watch area(s) touch this phase across ${item.impactedTasks.length} task(s).`
                    : "No current watch area is centered in this phase."}
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ borderRadius: 999, padding: "4px 9px", fontSize: 11, fontWeight: 800, color: "#e2e8f0", background: "rgba(148,163,184,0.12)", border: "1px solid rgba(148,163,184,0.22)" }}>
                    {item.impactedTasks.length} tasks
                  </span>
                  <span style={{ borderRadius: 999, padding: "4px 9px", fontSize: 11, fontWeight: 800, color: "#e2e8f0", background: "rgba(148,163,184,0.12)", border: "1px solid rgba(148,163,184,0.22)" }}>
                    {item.impactedHours}h
                  </span>
                  {item.riskCount > 0 && (
                    <span style={{ borderRadius: 999, padding: "4px 9px", fontSize: 11, fontWeight: 900, color: severity.color, background: `${severity.color}20`, border: `1px solid ${severity.color}55` }}>
                      {severity.watchLabel}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {risks.length === 0 ? (
        <div style={{ textAlign: "center", padding: "70px 20px", color: "#4ade80" }}>
          <div style={{ fontSize: 54, marginBottom: 12 }}>OK</div>
          <ShieldCheck size={36} style={{ margin: "0 auto 10px" }} />
          <p style={{ fontSize: 18, fontWeight: 800 }}>No supervisor watch areas are active in the current student plan</p>
        </div>
      ) : (
        SEVERITY_ORDER.filter((severity) => grouped[severity].length > 0).map((severity) => {
          const meta = SEVERITY_META[severity];
          const isOpen = openGroups[severity] ?? true;

          return (
            <section key={severity} style={{ marginBottom: 18 }}>
              <button
                onClick={() => setOpenGroups((current) => ({ ...current, [severity]: !isOpen }))}
                style={{
                  width: "100%",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  background: "rgba(15,23,42,0.9)",
                  border: "1px solid #1e293b",
                  borderRadius: 14,
                  padding: "13px 16px",
                  color: "#f8fafc",
                  cursor: "pointer",
                  marginBottom: isOpen ? 10 : 0,
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 9, fontWeight: 900 }}>
                  <span>{meta.icon}</span> {meta.watchLabel} ({grouped[severity].length})
                </span>
                <span style={{ color: "#64748b" }}>{isOpen ? "collapse" : "expand"}</span>
              </button>

              {isOpen && (
                <div style={{ display: "grid", gap: 12 }}>
                  {grouped[severity].map((item, index) => {
                    const category = categoryLabel(item.category);
                    const phases = unique(
                      (item.affected_tasks ?? [])
                        .map((taskId) => taskToPhase.get(taskId)?.title)
                        .filter((phase): phase is string => Boolean(phase)),
                    );
                    const owners = unique(
                      (item.affected_tasks ?? [])
                        .map((taskId) => taskMap.get(taskId)?.suggested_owner_role)
                        .filter((owner): owner is string => Boolean(owner)),
                    );
                    const deliverables = (item.affected_tasks ?? [])
                      .map((taskId) => taskMap.get(taskId))
                      .filter((task): task is Task => Boolean(task))
                      .map((task) => `${task.id}: ${formatTitle(task.title)}`);

                    return (
                      <div
                        key={`${severity}-${index}`}
                        style={{
                          background: "rgba(15,23,42,0.9)",
                          border: "1px solid #1e293b",
                          borderRadius: 16,
                          overflow: "hidden",
                        }}
                      >
                        <div style={{ display: "flex" }}>
                          <div style={{ width: 4, background: meta.color, flexShrink: 0 }} />
                          <div style={{ padding: 18, flex: 1 }}>
                            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
                              <span
                                style={{
                                  background: "rgba(255,255,255,0.06)",
                                  color: "#e2e8f0",
                                  borderRadius: 999,
                                  padding: "4px 9px",
                                  fontSize: 12,
                                  fontWeight: 800,
                                }}
                              >
                                {category}
                              </span>
                              <span
                                style={{
                                  background: `${meta.color}22`,
                                  color: meta.color,
                                  borderRadius: 999,
                                  padding: "4px 9px",
                                  fontSize: 12,
                                  fontWeight: 900,
                                }}
                              >
                                {meta.watchLabel}
                              </span>
                            </div>

                            <div style={{ fontSize: 18, fontWeight: 800, color: "#f8fafc", lineHeight: 1.4, marginBottom: 8 }}>
                              {item.message}
                            </div>
                            <div style={{ fontSize: 13, lineHeight: 1.6, color: "#94a3b8", marginBottom: 14 }}>
                              {categoryNote(item.category)}
                            </div>

                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10, marginBottom: 14 }}>
                              <div style={{ borderRadius: 12, border: "1px solid rgba(148,163,184,0.18)", background: "rgba(8,13,26,0.62)", padding: "12px 14px" }}>
                                <div style={{ color: "#64748b", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                                  Phase impact
                                </div>
                                <div style={{ color: "#f8fafc", fontWeight: 700, lineHeight: 1.5 }}>
                                  {phases.length ? phases.join(" -> ") : "Cross-plan watch item"}
                                </div>
                              </div>

                              <div style={{ borderRadius: 12, border: "1px solid rgba(148,163,184,0.18)", background: "rgba(8,13,26,0.62)", padding: "12px 14px" }}>
                                <div style={{ color: "#64748b", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                                  Owner watch
                                </div>
                                <div style={{ color: "#f8fafc", fontWeight: 700, lineHeight: 1.5 }}>
                                  {owners.length ? owners.join(", ") : "Supervisor review"}
                                </div>
                              </div>

                              <div style={{ borderRadius: 12, border: "1px solid rgba(148,163,184,0.18)", background: "rgba(8,13,26,0.62)", padding: "12px 14px" }}>
                                <div style={{ color: "#64748b", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                                  Student-plan deliverables
                                </div>
                                <div style={{ color: "#f8fafc", fontWeight: 700, lineHeight: 1.5 }}>
                                  {deliverables.length ? deliverables.slice(0, 3).join(" | ") : "No mapped tasks"}
                                </div>
                              </div>
                            </div>

                            {item.mitigation ? (
                              <div
                                style={{
                                  background: "rgba(56,189,248,0.08)",
                                  borderLeft: "3px solid #38bdf8",
                                  padding: 12,
                                  color: "#dbeafe",
                                  borderRadius: 10,
                                }}
                              >
                                <strong style={{ color: "#38bdf8" }}>Supervisor action: </strong>
                                {item.mitigation}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })
      )}

      {affectedTasks.length > 0 && (
        <section
          style={{
            background: "rgba(15,23,42,0.92)",
            border: "1px solid #1e293b",
            borderRadius: 18,
            padding: 22,
            marginTop: 18,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "#38bdf8", textTransform: "uppercase", marginBottom: 10 }}>
            Baseline Impact Snapshot
          </div>
          <div style={{ fontSize: 14, lineHeight: 1.65, color: "#cbd5e1" }}>
            Current watch areas touch <strong style={{ color: "#f8fafc" }}>{affectedTasks.length}</strong> task(s) across the student baseline, representing about <strong style={{ color: "#f8fafc" }}>{affectedHours} estimated hours</strong> of delivery work that deserves closer supervisor follow-up.
          </div>
        </section>
      )}
    </div>
  );
}
