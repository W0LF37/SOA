import { useMemo } from "react";
import { AlertTriangle, Calendar, CalendarDays, ClipboardList, Clock, GitBranch } from "lucide-react";

import { DEMO_ALL_DATA } from "../lib/demoProject";
import { buildExecutionRoadmap, buildPresentationTasks } from "../lib/presentation";
import { useAppStore } from "../lib/store";

const PHASE_COLORS = ["#0ea5e9", "#38bdf8", "#22c55e", "#14b8a6", "#a855f7", "#f97316"];
const LABEL_COLUMN_WIDTH = 260;

type GanttPhase = {
  key: string;
  title: string;
  goal: string;
  taskCount: number;
  totalHours: number;
  durationWeeks: number;
  startDay: number;
  durationDays: number;
  color: string;
  phaseNumber: number;
};

type GanttRow = {
  id: string;
  title: string;
  label: string;
  phaseTitle: string;
  phaseNumber: number;
  phaseColor: string;
  reqType: string;
  complexity: number | undefined;
  estimatedHours: number;
  durationDays: number;
  startDay: number;
  endDay: number;
  isCritical: boolean;
};

type GanttChartModel = {
  rows: GanttRow[];
  phases: GanttPhase[];
  phaseBoundaries: number[];
  tickDays: number[];
  totalDays: number;
};

function taskSequence(taskId: string | undefined) {
  if (!taskId) return Number.POSITIVE_INFINITY;
  const match = taskId.match(/(\d+)/);
  return match ? Number.parseInt(match[1], 10) : Number.POSITIVE_INFINITY;
}

function taskDays(task: { estimated_days?: number | null; estimated_hours?: number | null }) {
  if (typeof task.estimated_days === "number" && task.estimated_days > 0) return task.estimated_days;
  const hours = typeof task.estimated_hours === "number" ? task.estimated_hours : 8;
  return Math.max(1, Math.round(hours / 8));
}

function buildDependencyDepth(tasks: Array<{ id?: string; dependencies?: string[] }>) {
  const taskMap = new Map(tasks.map((task) => [task.id, task]));
  const memo = new Map<string, number>();
  const visiting = new Set<string>();

  function depth(taskId: string | undefined): number {
    if (!taskId) return 0;
    if (memo.has(taskId)) return memo.get(taskId) ?? 0;
    if (visiting.has(taskId)) return 0;

    visiting.add(taskId);
    const task = taskMap.get(taskId);
    const deps = (task?.dependencies ?? []).filter((dep) => taskMap.has(dep));
    const value = deps.length ? 1 + Math.max(...deps.map((dep) => depth(dep))) : 0;
    visiting.delete(taskId);
    memo.set(taskId, value);
    return value;
  }

  tasks.forEach((task) => {
    if (task.id) depth(task.id);
  });

  return memo;
}

function truncateLabel(value: string, max = 42) {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

export default function GanttPage() {
  const data = useAppStore((s) => s.data);
  const rawTasks = data?.tasks?.tasks?.length ? data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? [];
  const tasks = useMemo(() => buildPresentationTasks(rawTasks), [rawTasks]);
  const summary = data?.summary ?? DEMO_ALL_DATA.summary;
  const usingDemo = !(data?.tasks?.tasks?.length);
  const executionRoadmap = useMemo(() => buildExecutionRoadmap(tasks), [tasks]);

  const chart = useMemo<GanttChartModel>(() => {
    if (!tasks.length || !executionRoadmap.length) {
      return {
        rows: [],
        phases: [],
        phaseBoundaries: [],
        tickDays: [0, 7, 14],
        totalDays: 14,
      };
    }

    const criticalPathIds = new Set<string>(
      summary?.graph_analytics?.critical_path?.task_ids
      ?? DEMO_ALL_DATA.summary?.graph_analytics?.critical_path?.task_ids
      ?? [],
    );
    const depthMap = buildDependencyDepth(tasks);

    let phaseStartDay = 0;
    const phases: GanttPhase[] = [];
    const rows: GanttRow[] = [];

    executionRoadmap.forEach((phase, index) => {
      const phaseDurationDays = phase.durationWeeks * 7;
      const phaseColor = PHASE_COLORS[index % PHASE_COLORS.length];
      const orderedTasks = [...phase.tasks].sort((left, right) => taskSequence(left.id) - taskSequence(right.id));
      const phaseDepths = orderedTasks.map((task) => depthMap.get(task.id ?? "") ?? 0);
      const baseDepth = phaseDepths.length ? Math.min(...phaseDepths) : 0;

      phases.push({
        key: phase.key,
        title: phase.title,
        goal: phase.goal,
        taskCount: phase.tasks.length,
        totalHours: phase.totalHours,
        durationWeeks: phase.durationWeeks,
        startDay: phaseStartDay,
        durationDays: phaseDurationDays,
        color: phaseColor,
        phaseNumber: index + 1,
      });

      orderedTasks.forEach((task) => {
        const id = task.id ?? "Task";
        const durationDays = taskDays(task);
        const normalizedDepth = Math.max(0, (depthMap.get(id) ?? 0) - baseDepth);
        const localOffset = Math.min(normalizedDepth * 2, Math.max(phaseDurationDays - durationDays, 0));
        const startDay = phaseStartDay + localOffset;
        const endDay = startDay + durationDays;

        rows.push({
          id,
          title: task.title ?? "Task",
          label: `${id}: ${truncateLabel(task.title ?? "Task")}`,
          phaseTitle: phase.title,
          phaseNumber: index + 1,
          phaseColor,
          reqType: task.req_type ?? "FR",
          complexity: task.complexity,
          estimatedHours: typeof task.estimated_hours === "number" ? task.estimated_hours : 0,
          durationDays,
          startDay,
          endDay,
          isCritical: criticalPathIds.has(id),
        });
      });

      phaseStartDay += phaseDurationDays;
    });

    const totalDays = Math.max(phaseStartDay, ...rows.map((row) => row.endDay));
    const phaseBoundaries = phases.slice(1).map((phase) => phase.startDay);
    const tickDays: number[] = [];
    for (let day = 0; day <= totalDays; day += 7) tickDays.push(day);
    if (tickDays[tickDays.length - 1] !== totalDays) tickDays.push(totalDays);

    return {
      rows,
      phases,
      phaseBoundaries,
      tickDays,
      totalDays,
    };
  }, [executionRoadmap, summary, tasks]);

  return (
    <div className="fade-up">
      <h1 className="page-title">
        <Calendar size={22} /> Gantt Chart
      </h1>
      <p className="page-sub">Execution timeline aligned with the supervisor delivery plan and critical-path checkpoints</p>

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
          Live sprint data is unavailable, so this Gantt view is using the committee demo roadmap.
        </div>
      )}

      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {chart.phases.map((phase) => (
          <div key={String(phase.key)} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: 3,
                background: String(phase.color),
              }}
            />
            <span style={{ color: "#94a3b8" }}>
              Phase {phase.phaseNumber}: {phase.title}
            </span>
            <span style={{ color: "#475569" }}>({phase.durationWeeks}w)</span>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
          <div style={{ width: 12, height: 12, borderRadius: 3, background: "#ef4444" }} />
          <span style={{ color: "#94a3b8" }}>Critical Path</span>
        </div>
      </div>

      <div className="card" style={{ padding: 20, overflowX: "auto" }}>
        <div style={{ minWidth: 980 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `${LABEL_COLUMN_WIDTH}px 1fr`,
              alignItems: "end",
              marginBottom: 12,
            }}
          >
            <div />
            <div style={{ position: "relative", height: 28 }}>
              {chart.tickDays.map((day) => {
                const left = (day / chart.totalDays) * 100;
                return (
                  <div
                    key={day}
                    style={{
                      position: "absolute",
                      left: `${left}%`,
                      transform: day === 0 ? "translateX(0)" : "translateX(-50%)",
                      top: 6,
                      color: "#64748b",
                      fontSize: 12,
                    }}
                  >
                    {day}d
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ display: "grid", gap: 12 }}>
            {chart.rows.map((row) => (
              <div
                key={row.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: `${LABEL_COLUMN_WIDTH}px 1fr`,
                  gap: 14,
                  alignItems: "center",
                }}
              >
                <div title={row.title} style={{ color: "#94a3b8", fontSize: 11, lineHeight: 1.3, textAlign: "right" }}>
                  {row.label}
                </div>

                <div
                  style={{
                    position: "relative",
                    height: 28,
                    borderRadius: 999,
                    background: "#1e293b",
                    overflow: "hidden",
                  }}
                >
                  {chart.tickDays.slice(1).map((day) => (
                    <div
                      key={`${row.id}-tick-${day}`}
                      style={{
                        position: "absolute",
                        top: 0,
                        bottom: 0,
                        left: `${(day / chart.totalDays) * 100}%`,
                        borderLeft: "1px dashed rgba(148,163,184,0.18)",
                      }}
                    />
                  ))}

                  {chart.phaseBoundaries.map((day) => (
                    <div
                      key={`${row.id}-phase-${day}`}
                      style={{
                        position: "absolute",
                        top: 0,
                        bottom: 0,
                        left: `${(day / chart.totalDays) * 100}%`,
                        borderLeft: "1px solid rgba(125,211,252,0.22)",
                      }}
                    />
                  ))}

                  <div
                    title={`${row.id}: ${row.title}`}
                    style={{
                      position: "absolute",
                      left: `${(row.startDay / chart.totalDays) * 100}%`,
                      width: `${Math.max((row.durationDays / chart.totalDays) * 100, 2.8)}%`,
                      top: 0,
                      bottom: 0,
                      borderRadius: 999,
                      background: row.isCritical ? "#ef4444" : row.phaseColor,
                      boxShadow: row.isCritical ? "0 0 0 1px rgba(239,68,68,0.18)" : "none",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-3 fade-up fade-up-2" style={{ marginTop: 24 }}>
        {chart.phases.map((phase) => (
          <div
            key={String(phase.key)}
            className="card card-glow"
            style={{ borderTop: `3px solid ${String(phase.color)}` }}
          >
            <div className="card-title">Phase {phase.phaseNumber}</div>
            <div style={{ fontWeight: 800, fontSize: 15, marginBottom: 4 }}>{phase.title}</div>
            <div style={{ color: "#64748b", fontSize: 13, marginBottom: 10 }}>{phase.goal}</div>
            <div style={{ display: "flex", gap: 14, fontSize: 13, color: "#64748b", marginTop: 8, flexWrap: "wrap" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <Clock size={13} />
                {phase.totalHours}h
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <ClipboardList size={13} />
                {phase.taskCount} tasks
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <CalendarDays size={13} />
                {phase.durationWeeks}w
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <div className="page-title" style={{ marginBottom: 8 }}>
          <GitBranch size={18} /> Timeline Notes
        </div>
        <div style={{ display: "grid", gap: 10, color: "#94a3b8", fontSize: 14, lineHeight: 1.7 }}>
          <div>Critical-path tasks are highlighted in red and positioned according to the same dependency chain used in the supervisor dashboard.</div>
          <div>Phase ordering follows the execution baseline shown in `View Plan`, so registration and care delivery appear before reporting and hardening work.</div>
          <div style={{ color: "#fbbf24", display: "flex", alignItems: "center", gap: 8 }}>
            <AlertTriangle size={16} />
            Estimated offsets inside each phase are derived from task dependencies and effort bands, so they should be treated as supervisory planning guidance rather than fixed delivery dates.
          </div>
        </div>
      </div>
    </div>
  );
}
