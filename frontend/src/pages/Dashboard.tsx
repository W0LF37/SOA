import React, { useEffect, useMemo, useState, type ComponentType } from "react";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  GitBranch,
  ListChecks,
  RefreshCw,
  ShieldAlert,
  Timer,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useNavigate } from "react-router-dom";

import ProjectShowcase from "../components/ProjectShowcase";
import { analyzeMonitor, getChatMessages, type Task } from "../lib/api";
import { DEMO_ALL_DATA } from "../lib/demoProject";
import { buildPresentationTasks } from "../lib/presentation";
import { buildShowcaseData, formatQualityGate } from "../lib/projectShowcase";
import { useAppStore } from "../lib/store";

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function taskHours(task: Task) {
  return numberValue(task.estimated_hours);
}

function riskMeta(level: string) {
  const key = level.toLowerCase();
  if (key === "critical") return { color: "#ef4444", bg: "rgba(239,68,68,0.16)", label: "CRITICAL" };
  if (key === "high") return { color: "#f97316", bg: "rgba(249,115,22,0.16)", label: "HIGH" };
  if (key === "medium") return { color: "#eab308", bg: "rgba(234,179,8,0.16)", label: "MEDIUM" };
  if (key === "low") return { color: "#22c55e", bg: "rgba(34,197,94,0.16)", label: "LOW" };
  return { color: "#7dd3fc", bg: "rgba(148,163,184,0.14)", label: "UNKNOWN" };
}

function complexityColor(level: number | undefined) {
  if (level === 1) return "#22c55e";
  if (level === 2) return "#14b8a6";
  if (level === 3) return "#3b82f6";
  if (level === 4) return "#f97316";
  if (level === 5) return "#ef4444";
  return "#64748b";
}

function chartTooltip() {
  return {
    background: "#0f172a",
    border: "1px solid #334155",
    borderRadius: 8,
    color: "#f1f5f9",
  };
}

function MetricCard({
  label,
  value,
  color,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  color: string;
  icon: ComponentType<{ size?: number; color?: string }>;
}) {
  return (
    <div style={{
      background: "rgba(15,23,42,0.9)",
      border: "1px solid #1e293b",
      borderRadius: 16,
      padding: 20,
      borderTop: `3px solid ${color}`,
    }}>
      <div style={{
        width: 36,
        height: 36,
        borderRadius: 12,
        background: `${color}22`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        marginBottom: 14,
      }}>
        <Icon size={20} color={color} />
      </div>
      <div style={{ fontSize: "2.2rem", lineHeight: 1, fontWeight: 900, color: "#f8fafc" }}>
        {value}
      </div>
      <div style={{ marginTop: 8, fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800 }}>
        {label}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const data = useAppStore((state) => state.data);
  const brief = useAppStore((state) => state.brief);
  const loading = useAppStore((state) => state.loading);
  const error = useAppStore((state) => state.error);
  const refreshAll = useAppStore((state) => state.refreshAll);
  const auth = useAppStore((state) => state.auth);
  const navigate = useNavigate();
  const [monitoring, setMonitoring] = useState(false);
  const [planStatus, setPlanStatus] = useState<string | null>(null);
  const isLoading = data === null && !error;
  const usingDemo = !(data?.tasks?.tasks?.length);
  const showcase = buildShowcaseData(data, brief);

  const tasks = useMemo(
    () => buildPresentationTasks(data?.tasks?.tasks?.length ? data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? []),
    [data],
  );
  const riskReport = data?.risks ?? DEMO_ALL_DATA.risks ?? null;
  const summary = data?.summary ?? DEMO_ALL_DATA.summary ?? null;

  const totalHours = tasks.reduce((sum, task) => sum + taskHours(task), 0);
  const frCount = tasks.filter((task) => task.req_type === "FR").length;
  const nfrCount = tasks.filter((task) => task.req_type === "NFR").length;
  const riskLevel = riskReport?.risk_level ?? "unknown";
  const risk = riskMeta(riskLevel);
  const criticScore = summary?.critic?.score;
  const qualityGateLabel = formatQualityGate(criticScore);
  const generatedAt = (summary as { generated_at?: string } | null)?.generated_at;
  const projectName = showcase.title
    || (summary as { project_name?: string; plan_highlights?: { project_name?: string } } | null)?.project_name
    || (summary as { plan_highlights?: { project_name?: string } } | null)?.plan_highlights?.project_name
    || "Project Plan";

  const complexityData = [1, 2, 3, 4, 5].map((level) => ({
    level: `C${level}`,
    tasks: tasks.filter((task) => task.complexity === level).length,
  }));

  const topTasks = [...tasks]
    .sort((a, b) => taskHours(b) - taskHours(a))
    .slice(0, 8)
    .map((task) => ({
      name: task.id ?? task.title ?? "Task",
      hours: taskHours(task),
      title: task.title,
    }));

  const sprintCount = summary?.sprint_plan?.length ?? 0;
  const totalRisks = riskReport?.total_risks ?? riskReport?.risks?.length ?? 0;
  const dependencyPathIds =
    summary?.graph_analytics?.critical_path?.task_ids
    ?? DEMO_ALL_DATA.summary?.graph_analytics?.critical_path?.task_ids
    ?? [];
  const dependencyPathTasks = dependencyPathIds
    .map((taskId) => tasks.find((task) => task.id === taskId))
    .filter((task): task is Task => Boolean(task));
  const criticalPathCount = dependencyPathIds.length || dependencyPathTasks.length;
  const riskFocusSummary = showcase.riskFocus.length
    ? showcase.riskFocus.map((item) => item.replace(/\s*\(\d+\s+tasks?\)/i, "")).join("; ")
    : "Security, integration, and performance remain the primary review watch areas.";
  const supervisorHighlights = [
    `${qualityGateLabel} quality gate across ${tasks.length} planned task(s) and ${sprintCount} delivery sprint(s).`,
    criticalPathCount > 0
      ? `Critical path spans ${criticalPathCount} dependency-gated tasks: ${dependencyPathTasks.map((task) => task.id).join(" -> ")}.`
      : "Critical path is available in the task graph for dependency review.",
    `Primary supervisor watch areas: ${riskFocusSummary}.`,
  ];

  async function loadPlanStatus() {
    try {
      const response = await getChatMessages();
      setPlanStatus(response.plan_status ?? null);
    } catch {
      setPlanStatus(null);
    }
  }

  async function handleMonitor() {
    setMonitoring(true);
    await analyzeMonitor();
    await refreshAll();
    setMonitoring(false);
  }

  useEffect(() => {
    void loadPlanStatus();
  }, []);

  return (
    <>
      <section style={{
        width: "100%",
        borderRadius: 18,
        padding: "30px 34px",
        marginBottom: 22,
        background: "linear-gradient(135deg, #1e3a5f 0%, #0f172a 72%)",
        border: "1px solid #1e293b",
        position: "relative",
        overflow: "hidden",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 13, color: "#64748b", marginBottom: 4 }}>
              Welcome, {auth?.name ?? "Supervisor"}
            </div>
            <div style={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "#93c5fd", fontWeight: 800 }}>
              Supervisor Review Dashboard
            </div>
            <h1 style={{ margin: "8px 0 10px", fontSize: 34, color: "#f8fafc" }}>{projectName}</h1>
            <div style={{ color: "#7dd3fc", fontSize: 14, marginBottom: 14 }}>
              Generated: {generatedAt ? new Date(generatedAt).toLocaleString() : "n/a"}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className="stat-pill"><span style={{ color: "#7dd3fc", fontWeight: 900 }}>{tasks.length}</span><span className="stat-label">tasks</span></span>
              <span className="stat-pill"><span style={{ color: "#7dd3fc", fontWeight: 900 }}>{totalHours}h</span><span className="stat-label">estimated</span></span>
              <span className="stat-pill"><span style={{ color: "#22c55e", fontWeight: 900 }}>{sprintCount}</span><span className="stat-label">sprints</span></span>
              <span className="stat-pill"><span style={{ color: "#fca5a5", fontWeight: 900 }}>{criticalPathCount}</span><span className="stat-label">critical path</span></span>
            </div>
          </div>
          <div style={{
            background: "rgba(15,23,42,0.72)",
            border: "1px solid rgba(148,163,184,0.22)",
            borderRadius: 14,
            padding: "13px 18px",
            minWidth: 180,
          }}>
            <div style={{ color: "#64748b", fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Quality Gate
            </div>
            <div style={{ color: "#22c55e", fontSize: 28, fontWeight: 900 }}>
              {qualityGateLabel}
            </div>
          </div>
        </div>
        <div style={{ position: "absolute", right: 22, bottom: 14, color: "#64748b", fontSize: 12 }}>
          Last refreshed: {new Date().toLocaleTimeString()}
        </div>
      </section>

      <div className="button-row" style={{ marginBottom: 16 }}>
        <button className="secondary-btn" onClick={() => void refreshAll()}>
          <RefreshCw size={16} /> Refresh data
        </button>
        <a
          href="http://localhost:8000/api/export/tasks"
          download="ai_project_manager_tasks.xlsx"
          style={{ display: "flex", alignItems: "center", gap: 6, background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 8, padding: "8px 14px", color: "#4ade80", fontSize: 13, fontWeight: 600, textDecoration: "none" }}
        >
          Download Excel
        </a>
        <button className="primary-btn" disabled={monitoring} onClick={handleMonitor}>
          <GitBranch size={16} /> {monitoring ? "Refreshing..." : "Refresh project signals"}
        </button>
      </div>

      {loading ? <p className="muted">Loading project data...</p> : null}
      {error ? <p className="badge badge-red">{error}</p> : null}
      {usingDemo && (
        <div style={{ marginBottom: 14, borderRadius: 12, padding: "12px 16px", border: "1px solid rgba(59,130,246,0.25)", background: "rgba(59,130,246,0.08)", color: "#bfdbfe", fontSize: 13 }}>
          Live project data is unavailable, so the dashboard is showing the committee demo brief, task plan, and analytics preview.
        </div>
      )}

      <ProjectShowcase showcase={showcase} />

      {isLoading && (
        <div className="metrics-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 28 }}>
          {[1, 2, 3, 4].map((index) => (
            <div key={index} className="metric-card skeleton" style={{ height: 90 }} />
          ))}
        </div>
      )}

      {!isLoading && (
        <section className="metrics-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 16, marginBottom: 28 }}>
          <MetricCard label="Tasks Count" value={tasks.length} color="#3b82f6" icon={ListChecks} />
          <MetricCard label="Total Hours" value={totalHours} color="#a855f7" icon={Timer} />
          <MetricCard label="Quality Gate" value={qualityGateLabel} color="#22c55e" icon={CheckCircle2} />
          <MetricCard label="Key Risks" value={totalRisks} color={risk.color} icon={ShieldAlert} />
        </section>
      )}

      <section style={{
        background: "rgba(37,99,235,0.06)",
        border: "1px solid rgba(37,99,235,0.2)",
        borderRadius: 14,
        padding: 18,
        marginBottom: 14,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <CheckCircle2 size={17} color="#7dd3fc" />
          <span style={{ fontWeight: 700, color: "#f1f5f9" }}>Supervisor Highlights</span>
        </div>
        <div style={{ color: "#7dd3fc", fontSize: 14, lineHeight: 1.8 }}>
          {supervisorHighlights.map((line) => (
            <div key={line}>* {line}</div>
          ))}
        </div>
      </section>

      {(() => {
        const status = planStatus?.toLowerCase();
        if (status === "pending" || status === "needs_review") {
          return (
            <section style={{
              borderRadius: 12,
              padding: "12px 18px",
              display: "flex",
              alignItems: "center",
              gap: 12,
              background: "rgba(234,179,8,0.08)",
              border: "1px solid rgba(234,179,8,0.25)",
              color: "#eab308",
              marginBottom: 16,
            }}>
              <span style={{ fontWeight: 700 }}>A student plan is awaiting your review</span>
              <button
                onClick={() => navigate("/chat")}
                style={{
                  marginLeft: "auto",
                  color: "currentColor",
                  border: "1px solid currentColor",
                  borderRadius: 7,
                  padding: "5px 12px",
                  fontSize: 12,
                  background: "transparent",
                  fontWeight: 700,
                }}
              >
                Go to Chat -&gt;
              </button>
            </section>
          );
        }
        if (status === "approved") {
          return (
            <section style={{
              borderRadius: 12,
              padding: "12px 18px",
              display: "flex",
              alignItems: "center",
              gap: 12,
              background: "rgba(34,197,94,0.08)",
              border: "1px solid rgba(34,197,94,0.25)",
              color: "#22c55e",
              marginBottom: 16,
            }}>
              <span style={{ fontWeight: 700 }}>Plan Approved - Ready for Committee Brief</span>
              <button
                onClick={() => navigate("/brief")}
                style={{
                  marginLeft: "auto",
                  color: "currentColor",
                  border: "1px solid currentColor",
                  borderRadius: 7,
                  padding: "5px 12px",
                  fontSize: 12,
                  background: "transparent",
                  fontWeight: 700,
                }}
              >
                View Brief -&gt;
              </button>
            </section>
          );
        }
        return null;
      })()}

      <section style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: 16, marginBottom: 16 }}>
        <div
          className="card-glow"
          style={{
          background: "rgba(15,23,42,0.9)",
          border: "1px solid #1e293b",
          borderRadius: 16,
          padding: 20,
          }}
        >
          <div style={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 14 }}>
            Planning Distribution
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <h2 className="page-title"><Activity size={20} /> FR vs NFR</h2>
              <ResponsiveContainer width="100%" height={245}>
                <PieChart>
                  <Pie
                    data={[
                      { name: "FR", value: frCount },
                      { name: "NFR", value: nfrCount },
                    ]}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={55}
                    outerRadius={86}
                  >
                    <Cell fill="#3b82f6" />
                    <Cell fill="#f97316" />
                  </Pie>
                  <Tooltip contentStyle={chartTooltip()} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h2 className="page-title"><BarChart3 size={20} /> Complexity</h2>
              <ResponsiveContainer width="100%" height={245}>
                <BarChart data={complexityData}>
                  <CartesianGrid stroke="#334155" vertical={false} />
                  <XAxis dataKey="level" stroke="#7dd3fc" />
                  <YAxis stroke="#7dd3fc" allowDecimals={false} />
                  <Tooltip contentStyle={chartTooltip()} />
                  <Bar dataKey="tasks" radius={[6, 6, 0, 0]}>
                    {complexityData.map((item) => (
                      <Cell key={item.level} fill={complexityColor(Number(item.level.slice(1)))} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <div
          className="card-glow"
          style={{
          background: "rgba(15,23,42,0.9)",
          border: "1px solid #1e293b",
          borderRadius: 16,
          padding: 20,
          }}
        >
          <div style={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 14 }}>
            Plan Snapshot
          </div>
          <div style={{ display: "grid", gap: 13 }}>
            {[
              ["Review signal", showcase.confidence],
              ["Critical path", `${criticalPathCount} dependency-gated tasks`],
              ["Sprint count", sprintCount],
              ["Tracked risks", totalRisks],
            ].map(([label, value]) => (
              <div key={String(label)} style={{ display: "flex", justifyContent: "space-between", gap: 12, paddingBottom: 12, borderBottom: "1px solid #1e293b" }}>
                <span style={{ color: "#64748b", fontSize: 13 }}>{label}</span>
                <strong style={{ color: "#f8fafc", textAlign: "right" }}>{value}</strong>
              </div>
            ))}
            <div style={{ marginTop: 2 }}>
              <span style={{
                display: "inline-flex",
                padding: "5px 10px",
                borderRadius: 999,
                background: risk.bg,
                color: risk.color,
                fontWeight: 800,
                fontSize: 12,
              }}>
                Active watch: {totalRisks} area(s)
              </span>
            </div>
          </div>
        </div>
      </section>

      <section style={{
        background: "rgba(15,23,42,0.9)",
        border: "1px solid #1e293b",
        borderRadius: 16,
        padding: 20,
        marginBottom: 16,
      }}>
        <div style={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 12 }}>
          Top 8 Highest-Effort Tasks
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={topTasks} layout="vertical" margin={{ left: 24, right: 30 }}>
            <CartesianGrid stroke="#334155" horizontal={false} />
            <XAxis type="number" stroke="#7dd3fc" />
            <YAxis type="category" dataKey="name" stroke="#7dd3fc" width={75} />
            <Tooltip contentStyle={chartTooltip()} />
            <Bar dataKey="hours" fill="#a855f7" radius={[0, 7, 7, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </section>

      {(() => {
        if (!dependencyPathTasks.length) return null;
        return (
          <section style={{ background: "rgba(15,23,42,0.9)", border: "1px solid #1e293b", borderLeft: "4px solid #ef4444", borderRadius: 16, padding: 20, marginBottom: 16 }}>
            <div style={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "#ef4444", fontWeight: 800, marginBottom: 12 }}>
              Critical Path - {criticalPathCount} tasks | longest dependency chain
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              {dependencyPathTasks.map((t, i) => (
                <React.Fragment key={t.id}>
                  <span style={{ fontFamily: "monospace", background: "rgba(239,68,68,0.12)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.25)", padding: "5px 10px", borderRadius: 8, fontSize: 12, fontWeight: 700 }}>
                    {t.id}: {(t.title ?? "").slice(0, 30)}{(t.title ?? "").length > 30 ? "..." : ""}
                  </span>
                  {i < dependencyPathTasks.length - 1 && <span style={{ color: "#475569", fontSize: 16 }}>-&gt;</span>}
                </React.Fragment>
              ))}
            </div>
          </section>
        );
      })()}

      <section style={{
        background: "rgba(15,23,42,0.9)",
        border: "1px solid #1e293b",
        borderRadius: 16,
        padding: 20,
      }}>
        <div style={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 12 }}>
          Task Table
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Type</th>
                <th>Complexity</th>
                <th>Hours</th>
                <th>Skill</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task, index) => (
                <tr key={task.id ?? task.title} style={{ background: index % 2 === 0 ? "#0f172a" : "#0a0f1e", transition: "background 0.15s" }}>
                  <td>
                    <span style={{ fontFamily: "monospace", background: "rgba(59,130,246,0.14)", color: "#93c5fd", padding: "4px 8px", borderRadius: 8 }}>
                      {task.id}
                    </span>
                  </td>
                  <td>{task.title}</td>
                  <td>
                    <span className={`badge ${task.req_type === "NFR" ? "badge-orange" : "badge-blue"}`}>
                      {task.req_type}
                    </span>
                  </td>
                  <td>
                    <span style={{
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "3px 8px",
                      borderRadius: 999,
                      fontWeight: 800,
                      color: "#020617",
                      background: complexityColor(task.complexity),
                    }}>
                      C{task.complexity ?? "?"}
                    </span>
                  </td>
                  <td>{taskHours(task)}</td>
                  <td>{task.skill_required ?? "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
