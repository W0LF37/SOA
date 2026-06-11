import React, { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Calculator, ChevronDown, ChevronUp, Play, RefreshCw } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getPipelineInput, pipelineEventsUrl, runPipeline } from "../lib/api";
import { DEFAULT_PROJECT_BRIEF, DEMO_ALL_DATA } from "../lib/demoProject";
import { buildExecutionRoadmap, buildPresentationSprints, buildPresentationTasks, sortPresentationSprints } from "../lib/presentation";
import { buildShowcaseData, formatQualityGate } from "../lib/projectShowcase";
import { useAppStore } from "../lib/store";

type PipelineEvent = {
  type?: string;
  message?: string;
  data?: {
    task_count?: number;
    elapsed_seconds?: number;
  };
};

type CompletionData = {
  task_count: number;
  elapsed_seconds: number;
};

function parseEvent(event: MessageEvent<string>): PipelineEvent {
  try {
    return JSON.parse(event.data) as PipelineEvent;
  } catch {
    return { message: event.data };
  }
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function complexityColor(level: number | undefined) {
  if (level === 1) return "#22c55e";
  if (level === 2) return "#14b8a6";
  if (level === 3) return "#3b82f6";
  if (level === 4) return "#f97316";
  if (level === 5) return "#ef4444";
  return "#64748b";
}

function SupervisorTaskList({
  tasks,
  expandedTask,
  onToggleTask,
}: {
  tasks: Array<{
    id?: string;
    title?: string;
    req_type?: string;
    complexity?: number;
    estimated_hours?: number | null;
    suggested_owner_role?: string | null;
    skill_required?: string | null;
    description?: string;
    dependencies?: string[];
    estimated_days?: number | null;
    recommended_team_size?: number | null;
    confidence?: string;
  }>;
  expandedTask: string | null;
  onToggleTask: (taskId: string) => void;
}) {
  if (!tasks.length) return null;

  return (
    <section className="card">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <h2 className="page-title">Execution backlog</h2>
          <p className="muted" style={{ marginTop: -6 }}>
            Task-by-task execution review for the latest approved delivery baseline.
          </p>
        </div>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        {tasks.map((task) => {
          const id = task.id ?? task.title ?? "";
          const isExpanded = expandedTask === id;
          const color = complexityColor(task.complexity);

          return (
            <div
              key={id}
              onClick={() => onToggleTask(id)}
              style={{
                border: "1px solid #1e293b",
                borderRadius: 14,
                background: "rgba(15,23,42,0.78)",
                padding: "14px 16px",
                cursor: "pointer",
              }}
            >
              <div style={{ display: "grid", gridTemplateColumns: "80px 1fr 76px 82px 72px 170px 28px", gap: 12, alignItems: "center" }}>
                <span style={{ fontFamily: "monospace", background: "rgba(59,130,246,0.14)", color: "#93c5fd", padding: "5px 8px", borderRadius: 8, fontWeight: 800 }}>
                  {task.id}
                </span>
                <div style={{ color: "#f8fafc", fontWeight: 700, lineHeight: 1.35 }}>{task.title}</div>
                <span className={`badge ${task.req_type === "NFR" ? "badge-orange" : "badge-blue"}`}>{task.req_type}</span>
                <span style={{ display: "inline-flex", justifyContent: "center", borderRadius: 999, padding: "4px 8px", background: `${color}22`, color, fontWeight: 900 }}>
                  C{task.complexity}
                </span>
                <span style={{ color: "#cbd5e1", fontWeight: 800 }}>{task.estimated_hours ?? 0}h</span>
                <span style={{ color: "#7dd3fc", fontSize: 12 }}>{task.suggested_owner_role ?? task.skill_required ?? "n/a"}</span>
                {isExpanded ? <ChevronUp size={18} color="#94a3b8" /> : <ChevronDown size={18} color="#94a3b8" />}
              </div>

              {isExpanded && (
                <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 14 }}>
                  <div
                    style={{
                      background: "rgba(15,23,42,0.6)",
                      border: "1px solid #334155",
                      borderRadius: 10,
                      padding: 14,
                    }}
                  >
                    <div style={{ color: "#64748b", fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                      Description
                    </div>
                    <div style={{ color: "#cbd5e1", lineHeight: 1.6, fontSize: 13 }}>{task.description ?? "No description"}</div>
                  </div>

                  <div
                    style={{
                      background: "rgba(15,23,42,0.6)",
                      border: "1px solid #334155",
                      borderRadius: 10,
                      padding: 14,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#f8fafc", fontWeight: 800, marginBottom: 10 }}>
                      <Calculator size={16} color="#93c5fd" /> Review details
                    </div>
                    {[
                      ["Dependencies", task.dependencies?.length ? task.dependencies.join(", ") : "None"],
                      ["Owner", task.suggested_owner_role ?? "n/a"],
                      ["Skill", task.skill_required ?? "n/a"],
                      ["Estimated days", task.estimated_days ?? "n/a"],
                      ["Team size", task.recommended_team_size ?? "n/a"],
                      ["Confidence", task.confidence ?? "n/a"],
                    ].map(([label, value]) => (
                      <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid rgba(51,65,85,0.55)", gap: 12 }}>
                        <span style={{ color: "#7dd3fc" }}>{label}</span>
                        <strong style={{ color: "#e2e8f0", textAlign: "right" }}>{value}</strong>
                      </div>
                    ))}
                    <div style={{ marginTop: 10 }}>
                      <span className="badge badge-gray">Supervisor review</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function PlanPage() {
  const navigate = useNavigate();
  const role = useAppStore((state) => state.role);
  const data = useAppStore((state) => state.data);
  const brief = useAppStore((state) => state.brief);
  const [gitUrl, setGitUrl] = useState("");
  const [requirements, setRequirements] = useState(DEFAULT_PROJECT_BRIEF);
  const [useKb, setUseKb] = useState(true);
  const [step, setStep] = useState(1);
  const [status, setStatus] = useState("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [completionData, setCompletionData] = useState<CompletionData | null>(null);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const hasEditedRequirements = useRef(false);
  const refreshAll = useAppStore((state) => state.refreshAll);
  const refreshBrief = useAppStore((state) => state.refreshBrief);
  const tasksData = useAppStore((state) => state.data?.tasks?.tasks);
  const rawTasks = tasksData?.length ? tasksData : DEMO_ALL_DATA.tasks?.tasks ?? [];
  const tasks = useMemo(() => buildPresentationTasks(rawTasks), [rawTasks]);
  const usingDemoTasks = !(tasksData?.length);
  const summary = data?.summary ?? DEMO_ALL_DATA.summary;
  const showcase = buildShowcaseData(data, brief);
  const presentationSprints = useMemo(
    () => sortPresentationSprints(buildPresentationSprints(summary?.sprint_plan, tasks)),
    [summary?.sprint_plan, tasks],
  );
  const executionRoadmap = useMemo(
    () => buildExecutionRoadmap(tasks),
    [tasks],
  );

  const totalHours = tasks.reduce((sum, task) => sum + numberValue(task.estimated_hours), 0);
  const frCount = tasks.filter((task) => task.req_type === "FR").length;
  const nfrCount = tasks.filter((task) => task.req_type === "NFR").length;
  const taskCount = completionData?.task_count ?? tasks.length;
  const criticalPathIds = summary?.graph_analytics?.critical_path?.task_ids ?? [];
  const ownerBreakdown = Array.from(
    tasks.reduce((map, task) => {
      const key = task.suggested_owner_role ?? task.skill_required ?? "Unassigned";
      map.set(key, (map.get(key) ?? 0) + 1);
      return map;
    }, new Map<string, number>()),
  )
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5);
  const supervisorRiskFocus = showcase.riskFocus.length
    ? showcase.riskFocus
    : ["Execution watch areas will appear here once the risk register is available."];
  const stages = ["Parse", "Plan", "Estimate", "Validate", "Analyze"];
  const wizardSteps = ["Project Brief", "Enter Requirements", "Repository & Options", "Review & Generate"];
  const requirementsLines = requirements.trim() ? requirements.trim().split(/\r?\n/).length : 0;
  const isGenerating = status !== "idle" && status !== "failed" && !status.startsWith("completed");

  function stageIndex() {
    if (status === "idle") return -1;
    if (status === "starting") return 0;
    const normalized = status.toLowerCase();
    if (normalized.includes("plan") || normalized.includes("llm")) return 1;
    if (normalized.includes("estimat")) return 2;
    if (normalized.includes("critic") || normalized.includes("valid")) return 3;
    if (normalized.includes("complet") || normalized.includes("risk") || normalized.includes("graph")) return 4;
    return 1;
  }

  const currentStage = stageIndex();
  const isDone = status.startsWith("completed");

  useEffect(() => {
    return () => eventSourceRef.current?.close();
  }, []);

  useEffect(() => {
    let isActive = true;
    getPipelineInput()
      .then((payload) => {
        if (!isActive || hasEditedRequirements.current) return;
        if (payload.source === "default_sample" && payload.text.trim()) {
          setRequirements(payload.text);
        }
      })
      .catch(() => {
        // Keep local fallback sample when backend input is unavailable.
      });
    return () => {
      isActive = false;
    };
  }, []);

  if (role === "Supervisor") {
    const supervisorTaskCount = tasks.length;
    const supervisorTotalHours = totalHours;
    const supervisorCriticScore =
      (summary as { critic_score?: number; critic?: { score?: number } } | null)?.critic_score
      ?? summary?.critic?.score;
    const supervisorQualityGate = formatQualityGate(supervisorCriticScore);

    return (
      <section style={{ maxWidth: 1120, margin: "0 auto", padding: "32px 0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20, flexWrap: "wrap", marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 12, color: "#93c5fd", fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
              Execution Baseline
            </div>
            <h2 style={{ fontSize: "1.8rem", fontWeight: 900, color: "#f1f5f9", marginBottom: 8 }}>
              Supervisor Delivery Plan
            </h2>
            <p style={{ color: "#64748b", fontSize: 14, lineHeight: 1.7, maxWidth: 760 }}>
              This view uses the same project brief and generated task baseline shown to the student, but focuses on execution sequencing, ownership, and supervisor review checkpoints instead of committee storytelling.
            </p>
          </div>
          <div
            style={{
              minWidth: 260,
              borderRadius: 16,
              border: "1px solid #1e293b",
              background: "rgba(15,23,42,0.9)",
              padding: 18,
            }}
          >
            <div style={{ color: "#64748b", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8 }}>
              Baseline Source
            </div>
            <div style={{ color: "#f8fafc", fontSize: 22, fontWeight: 900, lineHeight: 1.25, marginBottom: 10 }}>
              {showcase.title}
            </div>
            <div style={{ color: "#7dd3fc", fontSize: 13 }}>
              Same brief alignment as the student workspace and supervisor dashboard.
            </div>
          </div>
        </div>
        {usingDemoTasks && (
          <div style={{ marginBottom: 18, borderRadius: 14, padding: "14px 16px", border: "1px solid rgba(59,130,246,0.25)", background: "rgba(59,130,246,0.08)", color: "#bfdbfe", fontSize: 13, lineHeight: 1.6 }}>
            Live plan data is unavailable, so this page is presenting the committee demo plan to keep the supervisor review complete and presentation-ready.
          </div>
        )}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 14, marginBottom: 24 }}>
          <div className="metric-card"><div className="metric-value">{supervisorTaskCount}</div><div className="metric-label">Execution Tasks</div></div>
          <div className="metric-card"><div className="metric-value">{Math.round(supervisorTotalHours)}h</div><div className="metric-label">Baseline Hours</div></div>
          <div className="metric-card"><div className="metric-value">{frCount} / {nfrCount}</div><div className="metric-label">FR / NFR Mix</div></div>
          <div className="metric-card"><div className="metric-value">{supervisorQualityGate}</div><div className="metric-label">Release Posture</div></div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1.35fr 1fr", gap: 16, marginBottom: 24 }}>
          <section className="card" style={{ margin: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
              <div>
                <h2 className="page-title">Delivery roadmap</h2>
                <p className="muted" style={{ marginTop: -6 }}>
                  Execution phases derived from the same student-approved scope and ordered by delivery value.
                </p>
              </div>
            </div>
            <div style={{ display: "grid", gap: 12 }}>
              {executionRoadmap.length ? executionRoadmap.map((phase, index) => (
                <div
                  key={`${phase.key}-${index}`}
                  style={{
                    border: "1px solid #1e293b",
                    borderRadius: 14,
                    padding: 16,
                    background: "rgba(15,23,42,0.78)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", marginBottom: 8, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{
                        width: 32,
                        height: 32,
                        borderRadius: 10,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: "rgba(59,130,246,0.16)",
                        color: "#7dd3fc",
                        fontWeight: 900,
                      }}>
                        {index + 1}
                      </span>
                      <div>
                        <div style={{ color: "#f8fafc", fontWeight: 800 }}>{phase.title}</div>
                        <div style={{ color: "#64748b", fontSize: 12 }}>{phase.goal}</div>
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span className="stat-pill"><span style={{ color: "#7dd3fc", fontWeight: 900 }}>{phase.tasks.length}</span><span className="stat-label">tasks</span></span>
                      <span className="stat-pill"><span style={{ color: "#22c55e", fontWeight: 900 }}>{phase.durationWeeks}w</span><span className="stat-label">duration</span></span>
                      <span className="stat-pill"><span style={{ color: "#a78bfa", fontWeight: 900 }}>{Math.round(numberValue(phase.totalHours))}h</span><span className="stat-label">effort</span></span>
                    </div>
                  </div>
                </div>
              )) : (
                <div style={{ color: "#64748b" }}>Sprint roadmap will appear here once the summary baseline is available.</div>
              )}
            </div>
          </section>

          <div style={{ display: "grid", gap: 16 }}>
            <section className="card" style={{ margin: 0 }}>
              <h2 className="page-title">Execution snapshot</h2>
              <div style={{ display: "grid", gap: 12, marginTop: 12 }}>
                {[
                  ["Brief alignment", "Matches the same clinic and telemedicine demo brief shown in the student workspace."],
                  ["Review signal", showcase.confidence],
                  ["Dependency chain", criticalPathIds.length ? `${criticalPathIds.length} gated tasks in the delivery chain` : "Dependency chain available after graph analysis"],
                  ["Sprint count", `${executionRoadmap.length || presentationSprints.length || summary?.sprint_plan?.length || 0} delivery sprint(s)`],
                ].map(([label, value]) => (
                  <div key={String(label)} style={{ paddingBottom: 12, borderBottom: "1px solid #1e293b" }}>
                    <div style={{ color: "#64748b", fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
                      {label}
                    </div>
                    <div style={{ color: "#f8fafc", lineHeight: 1.6 }}>{value}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="card" style={{ margin: 0 }}>
              <h2 className="page-title">Ownership coverage</h2>
              <p className="muted" style={{ marginTop: -6 }}>
                Execution ownership inferred from the generated task assignments.
              </p>
              <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
                {ownerBreakdown.map(([owner, count]) => (
                  <div
                    key={owner}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 14px",
                      borderRadius: 12,
                      background: "rgba(15,23,42,0.72)",
                      border: "1px solid #1e293b",
                    }}
                  >
                    <span style={{ color: "#f8fafc", fontWeight: 700 }}>{owner}</span>
                    <span style={{ color: "#7dd3fc", fontWeight: 800 }}>{count} task(s)</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="card" style={{ margin: 0 }}>
              <h2 className="page-title">Supervisor watch areas</h2>
              <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
                {supervisorRiskFocus.map((item) => (
                  <div
                    key={item}
                    style={{
                      padding: "12px 14px",
                      borderRadius: 12,
                      background: "rgba(15,23,42,0.72)",
                      border: "1px solid #1e293b",
                      color: "#f8fafc",
                      lineHeight: 1.6,
                    }}
                  >
                    {item}
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 24 }}>
          <button className="secondary-btn" onClick={() => void refreshAll()}>
            <RefreshCw size={16} /> Refresh tasks
          </button>
          <button className="primary-btn" onClick={() => navigate("/dashboard")}>Open Supervisor Dashboard -&gt;</button>
          <button className="secondary-btn" onClick={() => navigate("/gantt")}>Open Gantt View -&gt;</button>
        </div>
        <SupervisorTaskList
          tasks={tasks}
          expandedTask={expandedTask}
          onToggleTask={(taskId) => setExpandedTask((current) => current === taskId ? null : taskId)}
        />
      </section>
    );
  }

  /*
  if (false && role === "Supervisor") {
    const taskCount = data?.tasks?.tasks?.length ?? 0;
    const totalHours = data?.tasks?.tasks?.reduce((sum, task) => sum + (task.estimated_hours ?? 0), 0) ?? 0;
    const criticScore =
      (data?.summary as { critic_score?: number; critic?: { score?: number } } | null)?.critic_score
      ?? data?.summary?.critic?.score;

    return (
      <section style={{ maxWidth: 680, margin: "0 auto", padding: "32px 0" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 800, color: "#f1f5f9", marginBottom: 8 }}>Current Plan</h2>
        <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>Plans are generated by students. Review and approve from the Dashboard.</p>
        {taskCount > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginBottom: 24 }}>
            <div className="metric-card"><div className="metric-value">{taskCount}</div><div className="metric-label">Tasks</div></div>
            <div className="metric-card"><div className="metric-value">{Math.round(totalHours)}h</div><div className="metric-label">Estimated</div></div>
            <div className="metric-card"><div className="metric-value">{criticScore != null ? `${Math.round(criticScore * 100)}%` : "—"}</div><div className="metric-label">Critic Score</div></div>
          </div>
        ) : (
          <div style={{ color: "#475569", background: "#1e293b", borderRadius: 12, padding: "24px 20px", marginBottom: 24 }}>No plan generated yet. Ask a student to submit their project brief.</div>
        )}
        <button className="primary-btn" onClick={() => navigate("/dashboard")}>Go to Dashboard →</button>
      </section>
    );
  }

  */
  function attachEvents() {
    eventSourceRef.current?.close();
    const source = new EventSource(pipelineEventsUrl());
    eventSourceRef.current = source;

    const append = (line: string) => {
      setLogs((current) => [...current.slice(-120), line]);
    };

    source.addEventListener("heartbeat", (event) => {
      const payload = parseEvent(event as MessageEvent<string>);
      if (payload.message) append(payload.message);
    });
    source.addEventListener("status", (event) => {
      const payload = parseEvent(event as MessageEvent<string>);
      setStatus(payload.message ?? "running");
      append(payload.message ?? "Pipeline status updated");
    });
    source.addEventListener("log", (event) => {
      const payload = parseEvent(event as MessageEvent<string>);
      append(payload.message ?? "");
    });
    source.addEventListener("complete", (event) => {
      const payload = parseEvent(event as MessageEvent<string>);
      const count = payload.data?.task_count ?? 0;
      const elapsed = payload.data?.elapsed_seconds ?? 0;
      setCompletionData({ task_count: count, elapsed_seconds: elapsed });
      setStatus(`completed: ${count} tasks in ${elapsed}s`);
      append(payload.message ?? "Pipeline completed");
      void refreshAll();
      void refreshBrief();
      source.close();
    });
    source.addEventListener("error", (event) => {
      const payload = parseEvent(event as MessageEvent<string>);
      setError(payload.message ?? "Pipeline event stream failed.");
      source.close();
    });
  }

  async function handleRun() {
    const text = requirements.trim();
    if (!text) {
      setError("Requirements cannot be empty.");
      return;
    }

    setError(null);
    setLogs([]);
    setCompletionData(null);
    setStatus("starting");
    attachEvents();

    try {
      await runPipeline({
        requirements: text,
        input_format: "brief",
        use_kb: useKb,
      });
      setStatus("running");
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Pipeline failed to start.");
      setStatus("failed");
      eventSourceRef.current?.close();
    }
  }

  return (
    <>
      <section className="hero">
        <div>
          <p className="muted">Pipeline runner</p>
          <h1>Generate a project plan</h1>
          <p className="muted">
            Send requirements to the FastAPI backend and stream pipeline logs while
            tasks, risks, and summaries are regenerated.
          </p>
        </div>
        <div className="card">
          <span className="muted">Status</span>
          <div className="metric-value">{status}</div>
          {completionData ? (
            <p className="muted" style={{ margin: 0 }}>
              {completionData.task_count} tasks generated in {completionData.elapsed_seconds}s
            </p>
          ) : null}
        </div>
      </section>

      {status !== "idle" && (
        <div className="pipeline-stepper" style={{ marginBottom: 20 }}>
          {stages.map((stage, index) => (
            <React.Fragment key={stage}>
              <div className={`pipeline-step ${isDone || index < currentStage ? "done" : index === currentStage ? "active" : ""}`}>
                <div className="pipeline-step-dot">{isDone || index < currentStage ? "OK" : index + 1}</div>
                <span className="pipeline-step-label">{stage}</span>
              </div>
              {index < stages.length - 1 && (
                <div className={`pipeline-step-line ${isDone || index < currentStage ? "done" : ""}`} />
              )}
            </React.Fragment>
          ))}
        </div>
      )}

      <section className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 24, overflowX: "auto", paddingBottom: 4 }}>
          {wizardSteps.map((label, index) => {
            const stepNumber = index + 1;
            const completed = stepNumber < step;
            const current = stepNumber === step;

            return (
              <React.Fragment key={label}>
                <button
                  type="button"
                  onClick={() => {
                    if (completed) setStep(stepNumber);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    border: 0,
                    background: "transparent",
                    color: "inherit",
                    padding: 0,
                    cursor: completed ? "pointer" : "default",
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      width: 34,
                      height: 34,
                      borderRadius: "50%",
                      border: `2px solid ${completed ? "#22c55e" : current ? "#0284c7" : "#334155"}`,
                      background: completed ? "#22c55e" : current ? "#0284c7" : "#0f172a",
                      color: "#fff",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 12,
                      fontWeight: 800,
                      boxShadow: current ? "0 0 0 4px rgba(37,99,235,0.22)" : "none",
                    }}
                  >
                    {completed ? "OK" : stepNumber}
                  </span>
                  <span style={{ color: completed ? "#4ade80" : current ? "#94a3b8" : "#64748b", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
                    {label}
                  </span>
                </button>
                {index < wizardSteps.length - 1 && (
                  <div
                    style={{
                      flex: "0 0 36px",
                      height: 2,
                      background: completed ? "#22c55e" : "#1e293b",
                      margin: "0 8px",
                    }}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {step === 1 && (
          <>
            <div style={{ marginBottom: 18 }}>
              <h2 className="page-title" style={{ marginBottom: 8 }}>Project Brief Input</h2>
              <p className="page-sub" style={{ marginBottom: 0 }}>
                Planning now uses a single project brief flow for all generated plans.
              </p>
            </div>

            <div
              style={{
                marginBottom: 20,
                border: "1px solid rgba(37,99,235,0.35)",
                background: "rgba(37,99,235,0.12)",
                borderRadius: 16,
                padding: 18,
                color: "#f8fafc",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", marginBottom: 12 }}>
                <span style={{ fontSize: 24 }}>Project Brief</span>
                <span style={{ color: "#93c5fd", fontSize: 12, fontWeight: 800 }}>Selected</span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 8 }}>Free-form planning input</div>
              <div style={{ color: "#7dd3fc", lineHeight: 1.6 }}>
                Describe goals, scope, constraints, and expected outcomes in plain text. Structured template mode is no longer used here.
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="primary-btn" onClick={() => setStep(2)}>
                Next -&gt;
              </button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div style={{ marginBottom: 18 }}>
              <h2 className="page-title" style={{ marginBottom: 8 }}>Enter Requirements</h2>
              <p className="page-sub" style={{ marginBottom: 0 }}>
                Describe goals, core features, constraints, and expected outcomes in free-form text.
              </p>
            </div>

            <label className="field" style={{ marginBottom: 20 }}>
              <span>Project Requirements</span>
              <textarea
                rows={18}
                value={requirements}
                onChange={(event) => {
                  hasEditedRequirements.current = true;
                  setRequirements(event.target.value);
                }}
                style={{ resize: "vertical" }}
              />
            </label>

            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <button className="secondary-btn" onClick={() => setStep(1)}>
                &lt;- Back
              </button>
              <button className="primary-btn" onClick={() => setStep(3)} disabled={!requirements.trim()}>
                Next -&gt;
              </button>
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <div style={{ marginBottom: 18 }}>
              <h2 className="page-title" style={{ marginBottom: 8 }}>Repository &amp; Options</h2>
              <p className="page-sub" style={{ marginBottom: 0 }}>
                Add project context and decide whether to use the knowledge base for calibration.
              </p>
            </div>

            <label className="field" style={{ marginBottom: 20 }}>
              <span>GitHub Repository URL <small>(reference only)</small></span>
              <input
                type="url"
                value={gitUrl}
                onChange={(event) => setGitUrl(event.target.value)}
                placeholder="https://github.com/username/repo"
              />
            </label>

            <p className="muted" style={{ marginTop: -10, marginBottom: 20 }}>
              This repository link is stored as context only. The generated plan currently depends on the project brief text.
            </p>

            <div className="grid-2" style={{ marginBottom: 20 }}>
              {[
                {
                  value: true,
                  title: "Enable RAG",
                  description: "Use similar past projects to calibrate estimates",
                },
                {
                  value: false,
                  title: "Direct planning mode",
                  description: "Use local planning heuristics without knowledge-base calibration",
                },
              ].map((option) => {
                const selected = useKb === option.value;
                return (
                  <button
                    key={option.title}
                    type="button"
                    onClick={() => setUseKb(option.value)}
                    style={{
                      textAlign: "left",
                      border: `1px solid ${selected ? "#0284c7" : "#1e293b"}`,
                      background: selected ? "rgba(37,99,235,0.12)" : "rgba(15,23,42,0.72)",
                      borderRadius: 16,
                      padding: 18,
                      color: "#f8fafc",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start", marginBottom: 8 }}>
                      <div style={{ fontSize: 16, fontWeight: 800 }}>{option.title}</div>
                      {selected ? (
                        <span style={{ color: "#93c5fd", fontSize: 12, fontWeight: 800 }}>Selected</span>
                      ) : null}
                    </div>
                    <div style={{ color: "#7dd3fc", lineHeight: 1.6 }}>{option.description}</div>
                  </button>
                );
              })}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <button className="secondary-btn" onClick={() => setStep(2)}>
                &lt;- Back
              </button>
              <button className="primary-btn" onClick={() => setStep(4)}>
                Next -&gt;
              </button>
            </div>
          </>
        )}

        {step === 4 && (
          <>
            <div style={{ marginBottom: 18 }}>
              <h2 className="page-title" style={{ marginBottom: 8 }}>Review &amp; Generate</h2>
              <p className="page-sub" style={{ marginBottom: 0 }}>
                Confirm the plan inputs before starting the pipeline.
              </p>
            </div>

            <div style={{ display: "grid", gap: 10, marginBottom: 18 }}>
              {[
                { label: "Format", value: "Project Brief" },
                { label: "Requirements", value: `${requirementsLines} lines` },
                { label: "Repository", value: gitUrl.trim() || "Not provided" },
                { label: "Knowledge Base", value: useKb ? "Enable RAG" : "Direct planning mode" },
              ].map((row) => (
                <div
                  key={row.label}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 16,
                    alignItems: "center",
                    padding: "14px 16px",
                    borderRadius: 14,
                    background: "rgba(15,23,42,0.72)",
                    border: "1px solid #1e293b",
                  }}
                >
                  <span style={{ color: "#7dd3fc", fontSize: 13, fontWeight: 700 }}>{row.label}</span>
                  <span style={{ color: "#f8fafc", fontWeight: 700, textAlign: "right" }}>{row.value}</span>
                </div>
              ))}
            </div>

            {error ? <p className="badge badge-red">{error}</p> : null}

            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <button className="secondary-btn" onClick={() => setStep(3)}>
                &lt;- Back
              </button>
              <button className="primary-btn" disabled={isGenerating} onClick={() => void handleRun()}>
                <Play size={16} /> Generate Plan
              </button>
            </div>
          </>
        )}
      </section>

      <div className="terminal-window" style={{ marginTop: 16 }}>
        <div className="terminal-header">
          <div className="terminal-dot" style={{ background: "#ef4444" }} />
          <div className="terminal-dot" style={{ background: "#fbbf24" }} />
          <div className="terminal-dot" style={{ background: "#22c55e" }} />
          <span className="terminal-header-title">pipeline.log - AI Project Manager</span>
          {status !== "idle" && status !== "starting" && (
            <span style={{ marginLeft: "auto", fontSize: 11, color: status.startsWith("completed") ? "#4ade80" : "#7dd3fc" }}>
              {status.startsWith("completed") ? "done" : "running"}
            </span>
          )}
        </div>
        <div className="terminal-body">
          {logs.length ? logs.map((line, index) => {
            const normalized = line.toLowerCase();
            const cls = normalized.includes("error") || normalized.includes("fail") || normalized.includes("reject")
              ? "log-error"
              : normalized.includes("success") || normalized.includes("complet") || normalized.includes("approved")
              ? "log-success"
              : line.startsWith("[") || normalized.includes("starting") || normalized.includes("phase")
              ? "log-info"
              : normalized.includes("warn")
              ? "log-warn"
              : "";
            return <p key={index} className={`terminal-line ${cls}`}>{line}</p>;
          }) : (
            <p className="terminal-line terminal-empty">Waiting for pipeline to start...</p>
          )}
        </div>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <h2 className="page-title">Generated tasks</h2>
            <p className="muted" style={{ marginTop: -6 }}>
              Complete task output from the latest pipeline run.
            </p>
          </div>
          <button className="primary-btn" onClick={() => navigate("/gantt")}>
            View Gantt <ArrowRight size={16} />
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 16, marginTop: 10, marginBottom: 18 }}>
          {[
            { label: "Tasks", value: taskCount, color: "#3b82f6" },
            { label: "Estimated Hours", value: totalHours, color: "#a855f7" },
            { label: "FR / NFR", value: `${frCount} / ${nfrCount}`, color: "#22c55e" },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              style={{
                background: "rgba(15,23,42,0.9)",
                border: "1px solid #1e293b",
                borderRadius: 16,
                borderTop: `3px solid ${color}`,
                padding: 20,
              }}
            >
              <div className="metric-value" style={{ color }}>{value}</div>
              <div className="metric-label">{label}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gap: 10 }}>
          {tasks.length ? tasks.map((task) => {
            const id = task.id ?? task.title ?? "";
            const complexity = numberValue(task.complexity) || 1;
            const breakdown = task.estimation_breakdown ?? {};
            const baseHours = numberValue(breakdown.base_hours);
            const typeMultiplier = numberValue(breakdown.type_multiplier) || 1;
            const integrationOverhead = numberValue(breakdown.integration_overhead);
            const ragAdjustment = numberValue(breakdown.rag_adjustment_pct);
            const confidence = typeof breakdown.confidence === "string" ? breakdown.confidence : "n/a";
            const isExpanded = expandedTask === id;
            const color = complexityColor(task.complexity);

            return (
              <div
                key={id}
                onClick={() => setExpandedTask(isExpanded ? null : id)}
                style={{
                  border: "1px solid #1e293b",
                  borderRadius: 14,
                  background: "rgba(15,23,42,0.78)",
                  padding: "14px 16px",
                  cursor: "pointer",
                }}
              >
                <div style={{ display: "grid", gridTemplateColumns: "80px 1fr 76px 82px 72px 170px 28px", gap: 12, alignItems: "center" }}>
                  <span style={{ fontFamily: "monospace", background: "rgba(59,130,246,0.14)", color: "#93c5fd", padding: "5px 8px", borderRadius: 8, fontWeight: 800 }}>
                    {task.id}
                  </span>
                  <div style={{ color: "#f8fafc", fontWeight: 700, lineHeight: 1.35 }}>{task.title}</div>
                  <span className={`badge ${task.req_type === "NFR" ? "badge-orange" : "badge-blue"}`}>{task.req_type}</span>
                  <span style={{ display: "inline-flex", justifyContent: "center", borderRadius: 999, padding: "4px 8px", background: `${color}22`, color, fontWeight: 900 }}>
                    C{task.complexity}
                  </span>
                  <span style={{ color: "#cbd5e1", fontWeight: 800 }}>{task.estimated_hours ?? 0}h</span>
                  <span style={{ color: "#7dd3fc", fontSize: 12 }}>{task.suggested_owner_role ?? task.skill_required ?? "n/a"}</span>
                  {isExpanded ? <ChevronUp size={18} color="#94a3b8" /> : <ChevronDown size={18} color="#94a3b8" />}
                </div>

                {isExpanded && (
                  <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 14 }}>
                    <div
                      style={{
                        background: "rgba(15,23,42,0.6)",
                        border: "1px solid #334155",
                        borderRadius: 10,
                        padding: 14,
                      }}
                    >
                      <div style={{ color: "#64748b", fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                        Dependencies
                      </div>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {task.dependencies?.length ? task.dependencies.map((dependency) => (
                          <span key={dependency} style={{ fontFamily: "monospace", background: "rgba(255,255,255,0.06)", color: "#cbd5e1", padding: "4px 7px", borderRadius: 7 }}>
                            {dependency}
                          </span>
                        )) : (
                          <span style={{ color: "#475569" }}>No dependencies</span>
                        )}
                      </div>
                    </div>

                    <div
                      style={{
                        background: "rgba(15,23,42,0.6)",
                        border: "1px solid #334155",
                        borderRadius: 10,
                        padding: 14,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#f8fafc", fontWeight: 800, marginBottom: 10 }}>
                        <Calculator size={16} color="#93c5fd" /> Estimation Breakdown
                      </div>
                      {[
                        ["Base hours", baseHours ? `C${complexity} = ${baseHours}h` : "Backend calibrated"],
                        ["Type multiplier", `x${typeMultiplier}`],
                        ["Integration overhead", `+${integrationOverhead}h`],
                        ["RAG adjustment", `${ragAdjustment > 0 ? "+" : ""}${ragAdjustment}%`],
                        ["Confidence", confidence],
                        ["Total", `${task.estimated_hours ?? 0}h`],
                      ].map(([label, value]) => (
                        <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid rgba(51,65,85,0.55)" }}>
                          <span style={{ color: "#7dd3fc" }}>{label}</span>
                          <strong style={{ color: "#e2e8f0" }}>{value}</strong>
                        </div>
                      ))}
                      <div style={{ marginTop: 10 }}>
                        <span className="badge badge-gray">Backend estimate</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          }) : (
            <div className="muted" style={{ padding: 20, textAlign: "center" }}>No generated tasks yet.</div>
          )}
        </div>
      </section>
    </>
  );
}

