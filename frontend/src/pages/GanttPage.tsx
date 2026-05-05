import { useMemo } from "react";
import { Calendar, CalendarDays, ClipboardList, Clock } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  Cell, ResponsiveContainer, ReferenceLine,
} from "recharts";

import { useAppStore } from "../lib/store";

const SPRINT_COLORS = ["#2563eb", "#7c3aed", "#0891b2", "#059669", "#d97706"];

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div style={{
      background: "#1e293b",
      border: "1px solid #334155",
      borderRadius: 10,
      padding: "12px 16px",
      fontSize: 13,
    }}>
      <div style={{ fontWeight: 800, color: "#f1f5f9", marginBottom: 6 }}>
        {d.id}: {d.title}
      </div>
      <div style={{ color: "#94a3b8" }}>Sprint {d.sprint} · {d.req_type}</div>
      <div style={{ color: "#64748b", marginTop: 4 }}>
        {d.estimated_days}d · {d.estimated_hours}h · Complexity {d.complexity}
      </div>
      {d.is_critical && (
        <div style={{ color: "#ef4444", fontWeight: 700, marginTop: 4 }}>⚡ Critical Path</div>
      )}
    </div>
  );
}

export default function GanttPage() {
  const data = useAppStore((s) => s.data);

  const { rows, sprints, timelineEndMs } = useMemo(() => {
    const tasks = data?.tasks?.tasks;
    const sprintPlan = data?.summary?.sprint_plan;
    if (!tasks?.length || !sprintPlan?.length) {
      return { rows: [], sprints: [], timelineEndMs: 14 * 24 * 3600 * 1000 };
    }

    const cpIds = new Set<string>(
      data?.summary?.graph_analytics?.critical_path?.task_ids ?? [],
    );

    const sprintMap = new Map<string, number>();
    for (const sp of sprintPlan) {
      for (const tid of sp.tasks ?? []) sprintMap.set(tid, sp.sprint ?? 1);
    }

    const WEEK_MS = 7 * 24 * 3600 * 1000;
    const sprintOffsets = new Map<number, number>();
    let cum = 0;
    for (const sp of [...sprintPlan].sort((a, b) => (a.sprint ?? 1) - (b.sprint ?? 1))) {
      sprintOffsets.set(sp.sprint ?? 1, cum);
      cum += (sp.duration_weeks ?? 2) * WEEK_MS;
    }

    const rows = tasks.map((t) => {
      const sp = sprintMap.get(t.id ?? "") ?? 1;
      const off = sprintOffsets.get(sp) ?? 0;
      const days = t.estimated_days ?? Math.max(1, Math.round((t.estimated_hours ?? 8) / 8));
      const durMs = days * 24 * 3600 * 1000;
      return {
        ...t,
        sprint: sp,
        is_critical: cpIds.has(t.id ?? ""),
        startOffsetMs: off,
        durMs,
        label: `${t.id}: ${(t.title ?? "").slice(0, 36)}${(t.title ?? "").length > 36 ? "..." : ""}`,
      };
    }).sort((a, b) => a.sprint - b.sprint);

    return { rows, sprints: sprintPlan, timelineEndMs: Math.max(cum, ...rows.map((row) => row.durMs)) };
  }, [data]);

  if (!data?.tasks?.tasks?.length) {
    return (
      <div style={{ padding: 60, textAlign: "center", color: "#475569" }}>
        <Calendar size={48} style={{ margin: "0 auto 16px", opacity: 0.4 }} />
        <p style={{ fontSize: 16 }}>Run the pipeline first to see the Gantt chart.</p>
      </div>
    );
  }

  const sprintBoundaries: number[] = [];
  let elapsedMs = 0;
  for (const sprint of [...sprints].sort((a, b) => (a.sprint ?? 1) - (b.sprint ?? 1))) {
    if (elapsedMs > 0) sprintBoundaries.push(elapsedMs);
    elapsedMs += (sprint.duration_weeks ?? 2) * 7 * 24 * 3600 * 1000;
  }

  return (
    <div className="fade-up">
      <h1 className="page-title"><Calendar size={22} /> Gantt Chart</h1>
      <p className="page-sub">Sprint timeline with critical path highlighting</p>

      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {sprints.map((sp, i) => (
          <div key={sp.sprint} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, background: SPRINT_COLORS[i % SPRINT_COLORS.length] }} />
            <span style={{ color: "#94a3b8" }}>Sprint {sp.sprint}: {sp.name}</span>
            <span style={{ color: "#475569" }}>({sp.duration_weeks ?? 2}w)</span>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
          <div style={{ width: 12, height: 12, borderRadius: 3, background: "#ef4444" }} />
          <span style={{ color: "#94a3b8" }}>Critical Path</span>
        </div>
      </div>

      <div className="card" style={{ padding: "24px 12px" }}>
        <ResponsiveContainer width="100%" height={Math.max(300, rows.length * 44 + 60)}>
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ left: 8, right: 30, top: 8, bottom: 8 }}
            barSize={18}
          >
            <XAxis
              type="number"
              dataKey="durMs"
              domain={[0, timelineEndMs]}
              tickFormatter={(v) => `${Math.round(v / (24 * 3600 * 1000))}d`}
              tick={{ fill: "#64748b", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={240}
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            {sprintBoundaries.map((boundaryMs, i) => (
              <ReferenceLine key={i} x={boundaryMs} stroke="#334155" strokeDasharray="4 4" />
            ))}
            <Bar dataKey="durMs" background={{ fill: "#1e293b", radius: 6 }} radius={6}>
              {rows.map((row) => (
                <Cell
                  key={row.id}
                  fill={row.is_critical ? "#ef4444" : SPRINT_COLORS[(row.sprint - 1) % SPRINT_COLORS.length]}
                  opacity={0.9}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid-3 fade-up fade-up-2" style={{ marginTop: 24 }}>
        {sprints.map((sp, i) => (
          <div
            key={sp.sprint}
            className="card card-glow"
            style={{ borderTop: `3px solid ${SPRINT_COLORS[i % SPRINT_COLORS.length]}` }}
          >
            <div className="card-title">Sprint {sp.sprint}</div>
            <div style={{ fontWeight: 800, fontSize: 15, marginBottom: 4 }}>{sp.name}</div>
            <div style={{ color: "#64748b", fontSize: 13, marginBottom: 10 }}>
              {sp.goal ?? ""}
            </div>
            <div style={{ display: "flex", gap: 14, fontSize: 13, color: "#64748b", marginTop: 8 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Clock size={13} />{sp.total_estimated_hours ?? "?"}h</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><ClipboardList size={13} />{(sp.tasks ?? []).length} tasks</span>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><CalendarDays size={13} />{sp.duration_weeks ?? 2}w</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
