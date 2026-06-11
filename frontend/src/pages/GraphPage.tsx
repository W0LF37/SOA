import React, { useMemo, useState } from "react";
import { ArrowRight, GitBranch, Network } from "lucide-react";

import type { Task } from "../lib/api";
import { DEMO_ALL_DATA } from "../lib/demoProject";
import {
  buildExecutionRoadmap,
  buildPresentationTasks,
  type ExecutionRoadmapPhase,
} from "../lib/presentation";
import { useAppStore } from "../lib/store";

type TaskFilter = "all" | "critical" | "FR" | "NFR";

const PHASE_COLORS: Record<string, string> = {
  intake: "#38bdf8",
  clinical: "#5dd6ff",
  "diagnostics-finance": "#22c55e",
  "portal-communications": "#14b8a6",
  reporting: "#a855f7",
  hardening: "#f97316",
  remaining: "#94a3b8",
};

function phaseColor(key: string) {
  return PHASE_COLORS[key] ?? "#94a3b8";
}

function sequence(taskId: string | undefined) {
  if (!taskId) return Number.POSITIVE_INFINITY;
  const match = taskId.match(/(\d+)/);
  return match ? Number.parseInt(match[1], 10) : Number.POSITIVE_INFINITY;
}

function shortText(text: string | undefined, max = 56) {
  const value = text?.trim() ?? "";
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

function taskVisible(task: Task, filter: TaskFilter, criticalIds: Set<string>) {
  if (filter === "critical") return criticalIds.has(task.id ?? "");
  if (filter === "FR") return task.req_type === "FR";
  if (filter === "NFR") return task.req_type === "NFR";
  return true;
}

function TaskPill({
  label,
  color,
}: {
  label: string;
  color?: string;
}) {
  return (
    <span
      style={{
        borderRadius: 999,
        padding: "3px 9px",
        fontSize: 10,
        fontWeight: 700,
        color: "#e2e8f0",
        background: color ? `${color}20` : "rgba(148,163,184,0.12)",
        border: `1px solid ${color ? `${color}55` : "rgba(148,163,184,0.22)"}`,
      }}
    >
      {label}
    </span>
  );
}

function PhaseCard({
  phase,
  color,
}: {
  phase: ExecutionRoadmapPhase;
  color: string;
}) {
  return (
    <div
      style={{
        minWidth: 210,
        flex: "1 1 210px",
        borderRadius: 18,
        padding: "18px 18px 16px",
        border: `1px solid ${color}`,
        background: "linear-gradient(180deg, rgba(15,23,42,0.95), rgba(8,13,26,0.98))",
        boxShadow: `0 14px 30px ${color}14`,
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 800, color, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8 }}>
        Phase
      </div>
      <div style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.2, color: "#f8fafc", marginBottom: 8 }}>
        {phase.title}
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.55, color: "#94a3b8", marginBottom: 12 }}>
        {phase.goal}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <TaskPill label={`${phase.tasks.length} tasks`} color={color} />
        <TaskPill label={`${phase.durationWeeks}w`} color={color} />
        <TaskPill label={`${phase.totalHours}h`} color={color} />
      </div>
    </div>
  );
}

function TaskRow({
  task,
  phase,
  critical,
  dependencyTitles,
}: {
  task: Task;
  phase: ExecutionRoadmapPhase;
  critical: boolean;
  dependencyTitles: string[];
}) {
  const accent = critical ? "#ef4444" : phaseColor(phase.key);
  return (
    <div
      style={{
        borderRadius: 16,
        padding: "14px 16px",
        border: `1px solid ${accent}`,
        background: critical
          ? "linear-gradient(180deg, rgba(82,12,18,0.96), rgba(44,10,14,0.98))"
          : "linear-gradient(180deg, rgba(15,23,42,0.96), rgba(8,13,26,0.98))",
        boxShadow: critical
          ? "0 12px 30px rgba(239,68,68,0.16)"
          : `0 10px 24px ${accent}10`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 8, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, fontWeight: 800, color: accent, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            {task.id}
          </span>
          {critical && <TaskPill label="Critical" color="#ef4444" />}
          <TaskPill label={phase.title} color={phaseColor(phase.key)} />
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <TaskPill label={task.req_type} color={task.req_type === "NFR" ? "#f97316" : "#3b82f6"} />
          <TaskPill label={`C${task.complexity}`} color="#64748b" />
          <TaskPill label={`${task.estimated_hours ?? "?"}h`} color="#64748b" />
        </div>
      </div>

      <div style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.35, color: "#f8fafc", marginBottom: 8 }}>
        {task.title}
      </div>

      <div style={{ fontSize: 12, lineHeight: 1.55, color: "#94a3b8", marginBottom: 8 }}>
        Owner: {task.suggested_owner_role ?? "n/a"}
      </div>

      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, lineHeight: 1.55, color: "#cbd5e1" }}>
        <GitBranch size={14} style={{ marginTop: 2, color: accent, flexShrink: 0 }} />
        <div>
          {dependencyTitles.length
            ? `Depends on ${dependencyTitles.join(" -> ")}`
            : "No upstream dependency inside the current baseline."}
        </div>
      </div>
    </div>
  );
}

export default function GraphPage() {
  const data = useAppStore((s) => s.data);
  const [filter, setFilter] = useState<TaskFilter>("all");

  const tasksSource = useMemo(
    () => buildPresentationTasks(data?.tasks?.tasks?.length ? data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? []),
    [data],
  );
  const summary = data?.summary ?? DEMO_ALL_DATA.summary;
  const usingDemo = !(data?.tasks?.tasks?.length);

  const taskMap = useMemo(
    () => new Map(tasksSource.map((task) => [task.id, task])),
    [tasksSource],
  );

  const criticalIds = useMemo(
    () => new Set<string>(summary?.graph_analytics?.critical_path?.task_ids ?? []),
    [summary],
  );

  const executionRoadmap = useMemo(
    () => buildExecutionRoadmap(tasksSource),
    [tasksSource],
  );

  const criticalChain = useMemo(
    () =>
      (summary?.graph_analytics?.critical_path?.task_ids ?? [])
        .map((taskId) => taskMap.get(taskId))
        .filter((task): task is Task => Boolean(task)),
    [summary, taskMap],
  );

  const filteredRoadmap = useMemo(
    () =>
      executionRoadmap
        .map((phase) => ({
          ...phase,
          tasks: phase.tasks
            .filter((task) => taskVisible(task, filter, criticalIds))
            .sort((left, right) => sequence(left.id) - sequence(right.id)),
        }))
        .filter((phase) => phase.tasks.length > 0),
    [criticalIds, executionRoadmap, filter],
  );

  const visibleTasks = filteredRoadmap.flatMap((phase) => phase.tasks);

  return (
    <div className="fade-up">
      <h1 className="page-title">
        <Network size={22} /> Dependency Graph
      </h1>
      <p className="page-sub">Committee-friendly dependency view with explicit arrows, critical-task sequencing, and phase handoffs</p>

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
          Live dependency positions are unavailable, so the supervisor view is showing the committee demo dependency structure aligned with the same execution baseline used in View Plan.
        </div>
      )}

      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        {[
          { color: "#3b82f6", label: "Functional (FR)" },
          { color: "#f97316", label: "Non-Functional (NFR)" },
          { color: "#ef4444", label: "Critical Path" },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, background: color }} />
            <span style={{ color: "#94a3b8" }}>{label}</span>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 18, alignItems: "center", flexWrap: "wrap" }}>
        {(["all", "critical", "FR", "NFR"] as const).map((value) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            style={{
              padding: "6px 14px",
              borderRadius: 20,
              fontSize: 12,
              cursor: "pointer",
              border: "none",
              background: filter === value ? "#3b82f6" : "#1e293b",
              color: filter === value ? "#fff" : "#94a3b8",
            }}
          >
            {value === "critical" ? "Critical" : value === "all" ? "All" : value}
          </button>
        ))}
        <span style={{ color: "#475569", fontSize: 12 }}>{visibleTasks.length} tasks</span>
      </div>

      <section
        style={{
          borderRadius: 22,
          padding: "22px",
          border: "1px solid rgba(239,68,68,0.24)",
          background: "linear-gradient(180deg, rgba(15,23,42,0.96), rgba(8,13,26,0.98))",
          marginBottom: 18,
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "#ef4444", textTransform: "uppercase", marginBottom: 10 }}>
          Primary Dependency Chain
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.65, color: "#cbd5e1", marginBottom: 18 }}>
          The committee should be able to read the main gated path at a glance. Each red step depends on the previous one and drives release timing.
        </div>

        <div style={{ display: "flex", alignItems: "stretch", gap: 10, flexWrap: "wrap" }}>
          {criticalChain.map((task, index) => {
            const phase = executionRoadmap.find((item) => item.tasks.some((candidate) => candidate.id === task.id));
            return (
              <React.Fragment key={task.id}>
                <div
                  style={{
                    minWidth: 214,
                    flex: "1 1 214px",
                    borderRadius: 18,
                    padding: "16px",
                    border: "1px solid #ef4444",
                    background: "linear-gradient(180deg, rgba(82,12,18,0.96), rgba(44,10,14,0.98))",
                    boxShadow: "0 12px 28px rgba(239,68,68,0.16)",
                  }}
                >
                  <div style={{ fontSize: 11, fontWeight: 800, color: "#fca5a5", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8 }}>
                    {task.id}
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.35, color: "#f8fafc", marginBottom: 10 }}>
                    {task.title}
                  </div>
                  {phase && <TaskPill label={phase.title} color={phaseColor(phase.key)} />}
                </div>
                {index < criticalChain.length - 1 && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      minWidth: 34,
                      color: "#ef4444",
                    }}
                  >
                    <ArrowRight size={26} />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </section>

      <section
        style={{
          borderRadius: 22,
          padding: "22px",
          border: "1px solid rgba(56,189,248,0.18)",
          background: "linear-gradient(180deg, rgba(15,23,42,0.96), rgba(8,13,26,0.98))",
          marginBottom: 18,
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "#38bdf8", textTransform: "uppercase", marginBottom: 10 }}>
          Phase Handoff Map
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.65, color: "#cbd5e1", marginBottom: 18 }}>
          This is the simplified supervisor view of how delivery moves from intake into care workflows, then financial and portal work, and finally review and hardening.
        </div>

        <div style={{ display: "flex", alignItems: "stretch", gap: 10, flexWrap: "wrap" }}>
          {executionRoadmap.map((phase, index) => {
            const color = phaseColor(phase.key);
            return (
              <React.Fragment key={phase.key}>
                <PhaseCard phase={phase} color={color} />
                {index < executionRoadmap.length - 1 && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      minWidth: 34,
                      color,
                    }}
                  >
                    <ArrowRight size={24} />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </section>

      <section
        style={{
          borderRadius: 22,
          padding: "22px",
          border: "1px solid rgba(56,189,248,0.18)",
          background: "linear-gradient(180deg, rgba(15,23,42,0.96), rgba(8,13,26,0.98))",
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "#38bdf8", textTransform: "uppercase", marginBottom: 10 }}>
          Task Dependency Clusters
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.65, color: "#cbd5e1", marginBottom: 18 }}>
          Each task now states its upstream dependencies directly, so the graph reads clearly even without floating arrows across the whole canvas.
        </div>

        <div style={{ display: "grid", gap: 18 }}>
          {filteredRoadmap.map((phase) => (
            <div
              key={phase.key}
              style={{
                borderRadius: 20,
                border: `1px solid ${phaseColor(phase.key)}44`,
                background: "rgba(8,13,26,0.55)",
                padding: "18px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: "#f8fafc", marginBottom: 6 }}>
                    {phase.title}
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.55, color: "#94a3b8" }}>
                    {phase.goal}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <TaskPill label={`${phase.tasks.length} tasks`} color={phaseColor(phase.key)} />
                  <TaskPill label={`${phase.durationWeeks}w`} color={phaseColor(phase.key)} />
                  <TaskPill label={`${phase.totalHours}h`} color={phaseColor(phase.key)} />
                </div>
              </div>

              <div style={{ display: "grid", gap: 12 }}>
                {phase.tasks.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    phase={phase}
                    critical={criticalIds.has(task.id ?? "")}
                    dependencyTitles={(task.dependencies ?? [])
                      .map((dependencyId) => taskMap.get(dependencyId))
                      .filter((dependency): dependency is Task => Boolean(dependency))
                      .sort((left, right) => sequence(left.id) - sequence(right.id))
                      .map((dependency) => `${dependency.id}: ${shortText(dependency.title, 42)}`)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
