import { useEffect, useState } from "react";
import { Activity, GitCommit, CheckCircle, Circle, Clock } from "lucide-react";

import { analyzeMonitor } from "../lib/api";
import { useAppStore } from "../lib/store";

type TaskProgress = {
  task_id: string;
  task_title: string;
  status: "completed" | "in_progress" | "not_started";
  matched_commits: string[];
  evidence?: string[];
  completion_estimate: number;
};

type FullMonitorReport = {
  overall_progress: number;
  tasks_completed: number;
  tasks_in_progress: number;
  tasks_not_started: number;
  commits_analyzed: number;
  task_progress: TaskProgress[];
  behind_schedule?: string[];
};

const STATUS_META = {
  completed:   { icon: CheckCircle, color: "#4ade80", bg: "rgba(22,163,74,0.15)",  label: "Completed" },
  in_progress: { icon: Clock,       color: "#60a5fa", bg: "rgba(37,99,235,0.15)",  label: "In Progress" },
  not_started: { icon: Circle,      color: "#475569", bg: "rgba(71,85,105,0.15)",  label: "Not Started" },
};

function toMonitorError(error: unknown) {
  if (typeof error === "object" && error !== null) {
    const maybeAxios = error as { response?: { data?: { detail?: string } }; message?: string };
    return maybeAxios.response?.data?.detail ?? maybeAxios.message ?? "Monitor failed";
  }
  return "Monitor failed";
}

export default function MonitorPage() {
  const [repoPath, setRepoPath] = useState("");
  const [report, setReport] = useState<FullMonitorReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const storeMonitor = useAppStore((s) => s.data?.monitor);

  useEffect(() => {
    if (storeMonitor) setReport(storeMonitor as unknown as FullMonitorReport);
  }, [storeMonitor]);

  async function analyze() {
    setLoading(true);
    setError("");
    setReport(null);
    setExpandedTask(null);
    try {
      const result = await analyzeMonitor(repoPath.trim() || undefined);
      setReport(result as unknown as FullMonitorReport);
    } catch (monitorError) {
      setError(toMonitorError(monitorError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fade-up">
      <h1 className="page-title"><Activity size={22} /> Git Monitor</h1>
      <p className="page-sub">Track implementation progress by analyzing git commits</p>

      <div className="card" style={{ marginBottom: 24, display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="field" style={{ flex: 1, marginBottom: 0, minWidth: 240 }}>
          <label>Git Repository Path</label>
          <input
            value={repoPath}
            onChange={e => setRepoPath(e.target.value)}
            placeholder="Optional: C:\\path\\to\\repo or leave empty"
            onKeyDown={e => e.key === "Enter" && void analyze()}
          />
        </div>
        <button
          className="btn btn-primary"
          onClick={() => void analyze()}
          disabled={loading}
          style={{ flexShrink: 0 }}
        >
          <Activity size={16} />
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </div>

      {error && (
        <div style={{
          background: "rgba(185,28,28,0.12)", border: "1px solid rgba(185,28,28,0.3)",
          borderRadius: 12, padding: "14px 18px", marginBottom: 20, color: "#f87171",
        }}>
          {error}
        </div>
      )}

      {report && (
        <>
          <div className="card fade-up" style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span style={{ color: "#94a3b8", fontSize: 14 }}>Overall Progress</span>
              <span style={{ fontSize: 28, fontWeight: 900, color: "#f1f5f9" }}>
                {Math.round((report.overall_progress ?? 0) * 100)}%
              </span>
            </div>
            <div className="progress-bar-track">
              <div className="progress-bar-fill" style={{
                width: `${(report.overall_progress ?? 0) * 100}%`,
                background: (report.overall_progress ?? 0) >= 0.8 ? "#4ade80"
                  : (report.overall_progress ?? 0) >= 0.4 ? "#60a5fa" : "#f59e0b",
              }} />
            </div>
          </div>

          <div className="metric-grid fade-up fade-up-1" style={{ marginBottom: 20 }}>
            {[
              { label: "Commits Analyzed", value: report.commits_analyzed ?? 0,   color: "#3b82f6" },
              { label: "Completed",         value: report.tasks_completed ?? 0,    color: "#4ade80" },
              { label: "In Progress",       value: report.tasks_in_progress ?? 0,  color: "#60a5fa" },
              { label: "Not Started",       value: report.tasks_not_started ?? 0,  color: "#475569" },
            ].map(({ label, value, color }) => (
              <div key={label} className="metric-card" style={{ borderTop: `3px solid ${color}` }}>
                <div className="metric-value" style={{ color }}>{value}</div>
                <div className="metric-label">{label}</div>
              </div>
            ))}
          </div>

          {(report.behind_schedule ?? []).length > 0 && (
            <div style={{
              background: "rgba(185,28,28,0.1)", border: "1px solid rgba(185,28,28,0.25)",
              borderRadius: 12, padding: "14px 18px", marginBottom: 20,
            }}>
              <div style={{ fontWeight: 700, color: "#f87171", marginBottom: 4 }}>⚠ Behind Schedule</div>
              <div style={{ color: "#fca5a5", fontSize: 14 }}>
                {(report.behind_schedule ?? []).join(" · ")}
              </div>
            </div>
          )}

          <div className="grid-3 fade-up fade-up-2">
            {(report.task_progress ?? []).map(tp => {
              const meta = STATUS_META[tp.status] ?? STATUS_META.not_started;
              const Icon = meta.icon;
              const pct = Math.round((tp.completion_estimate ?? 0) * 100);
              return (
                <div
                  key={tp.task_id}
                  className="card"
                  style={{ borderLeft: `4px solid ${meta.color}`, cursor: "pointer" }}
                  onClick={() => setExpandedTask(expandedTask === tp.task_id ? null : tp.task_id)}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: 12, color: meta.color }}>{tp.task_id}</div>
                      <div style={{ fontSize: 13, color: "#f1f5f9", marginTop: 2, lineHeight: 1.3 }}>
                        {tp.task_title.slice(0, 50)}{tp.task_title.length > 50 ? "..." : ""}
                      </div>
                    </div>
                    <div style={{
                      background: meta.bg, borderRadius: 8, padding: "4px 8px",
                      display: "flex", alignItems: "center", gap: 4,
                      fontSize: 11, color: meta.color, flexShrink: 0,
                    }}>
                      <Icon size={12} /> {meta.label}
                      <div style={{ fontSize: 10, color: "#334155", marginTop: 4 }}>
                        {expandedTask === tp.task_id ? "▲ collapse" : "▼ tap for commits"}
                      </div>
                    </div>
                  </div>
                  <div className="progress-bar-track" style={{ marginBottom: 8 }}>
                    <div className="progress-bar-fill" style={{ width: `${pct}%`, background: meta.color }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#64748b" }}>
                    <span>{pct}% complete</span>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <GitCommit size={11} />{tp.matched_commits.length} commits
                    </span>
                  </div>

                  {expandedTask === tp.task_id && (
                    <div style={{ marginTop: 10, borderTop: "1px solid #1e293b", paddingTop: 10 }}>
                      <div style={{ fontSize: 11, color: "#475569", marginBottom: 6 }}>Matched Commits:</div>
                      {tp.matched_commits.length === 0 ? (
                        <div style={{ color: "#334155", fontSize: 12 }}>No commits matched yet</div>
                      ) : tp.matched_commits.map((sha, i) => (
                        <div key={`${sha}-${i}`} style={{ fontSize: 11, color: "#64748b", fontFamily: "monospace", marginBottom: 3 }}>
                          <span style={{ color: "#3b82f6" }}>{sha.slice(0, 7)}</span>
                          {" — "}{tp.evidence?.[i] ?? sha}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {!report && !loading && !error && (
        <div style={{ textAlign: "center", padding: "60px 20px", color: "#475569" }}>
          <GitCommit size={48} style={{ margin: "0 auto 16px", opacity: 0.4 }} />
          <p style={{ fontSize: 15 }}>Enter a repository path, or leave it empty to mark all tasks as not started.</p>
          <p style={{ fontSize: 13, marginTop: 8 }}>
            Run <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>
              python scripts/generate_demo_repo.py
            </code> to create a demo repo.
          </p>
        </div>
      )}
    </div>
  );
}
