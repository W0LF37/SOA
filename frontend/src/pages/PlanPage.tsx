import React, { useEffect, useRef, useState } from "react";
import { ArrowRight, Calculator, ChevronDown, ChevronUp, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { getPipelineInput, pipelineEventsUrl, runPipeline } from "../lib/api";
import { useAppStore } from "../lib/store";

const BRIEF_FALLBACK = `Project Title:
Clinic Management System

Project Overview:
A web-based system to manage clinic operations including patient registration,
appointments, consultations, and billing.

Problem Statement:
Clinic staff currently manage patient records and appointments on paper,
leading to errors, duplicate records, and inefficient scheduling.

Proposed Solution:
Build a unified digital platform where receptionists, doctors, and billing
staff can collaborate on a single patient record.

Main Features:
- Register new patients using national ID and contact details
- Book and manage patient appointments for available doctors
- Allow doctors to view patient history and record diagnosis
- Generate itemized invoices for consultations and lab tests
- Send automated email notifications for deadlines

Constraints or Special Notes:
- Must support both Arabic and English languages
- System must respond within two seconds for all standard operations`;

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

export default function PlanPage() {
  const navigate = useNavigate();
  const role = useAppStore((state) => state.role);
  const data = useAppStore((state) => state.data);
  const [gitUrl, setGitUrl] = useState("");
  const [requirements, setRequirements] = useState(BRIEF_FALLBACK);
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
  const tasks = tasksData ?? [];

  const totalHours = tasks.reduce((sum, task) => sum + numberValue(task.estimated_hours), 0);
  const frCount = tasks.filter((task) => task.req_type === "FR").length;
  const nfrCount = tasks.filter((task) => task.req_type === "NFR").length;
  const taskCount = completionData?.task_count ?? tasks.length;
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
        if (payload.text.trim()) {
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
                      border: `2px solid ${completed ? "#22c55e" : current ? "#2563eb" : "#334155"}`,
                      background: completed ? "#22c55e" : current ? "#2563eb" : "#0f172a",
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
                  <span style={{ color: completed ? "#4ade80" : current ? "#60a5fa" : "#64748b", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
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
              <div style={{ color: "#94a3b8", lineHeight: 1.6 }}>
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
                  title: "Rule-based only",
                  description: "Use fixed complexity-hour formulas without KB",
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
                      border: `1px solid ${selected ? "#2563eb" : "#1e293b"}`,
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
                    <div style={{ color: "#94a3b8", lineHeight: 1.6 }}>{option.description}</div>
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
                { label: "Knowledge Base", value: useKb ? "Enable RAG" : "Rule-based only" },
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
                  <span style={{ color: "#94a3b8", fontSize: 13, fontWeight: 700 }}>{row.label}</span>
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
          <span className="terminal-header-title">pipeline.log - CritiPlan</span>
          {status !== "idle" && status !== "starting" && (
            <span style={{ marginLeft: "auto", fontSize: 11, color: status.startsWith("completed") ? "#4ade80" : "#60a5fa" }}>
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
                  <span style={{ color: "#94a3b8", fontSize: 12 }}>{task.suggested_owner_role ?? task.skill_required ?? "n/a"}</span>
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
                          <span style={{ color: "#94a3b8" }}>{label}</span>
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
