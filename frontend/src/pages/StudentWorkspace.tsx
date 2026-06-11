import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import {
  Send,
  RefreshCw,
  CheckCircle,
  MessageSquare,
  ListChecks,
  Timer,
  ShieldAlert,
  FileText,
  Cpu,
  ShieldCheck,
  Calendar,
  AlertTriangle,
  Sparkles,
  ChevronDown,
  ChevronUp,
  LogOut,
  Star,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  API_BASE_URL,
  getPipelineInput,
  runPipeline,
  pipelineEventsUrl,
  getChatMessages,
  sendChatMessage,
  type ChatMessage,
} from "../lib/api";
import ExplainPopup from "../components/ExplainPopup";
import ProjectShowcase from "../components/ProjectShowcase";
import { DEFAULT_PROJECT_BRIEF, DEMO_ALL_DATA, PROJECT_SAMPLES } from "../lib/demoProject";
import { buildPresentationSprints, buildPresentationTasks, sortPresentationSprints } from "../lib/presentation";
import { buildShowcaseData, formatQualityGate } from "../lib/projectShowcase";
import { useAppStore } from "../lib/store";

// ── Sample briefs ────────────────────────────────────────────────────────────

const SAMPLES: Record<string, string> = PROJECT_SAMPLES;

// ── Pipeline stage detection ─────────────────────────────────────────────────

type Stage = { id: string; label: string; icon: React.ComponentType<{ size?: number; color?: string }> };

const STAGES: Stage[] = [
  { id: "parse",  label: "Parsing Requirements",  icon: FileText },
  { id: "plan",   label: "AI Planning Tasks",      icon: Cpu },
  { id: "effort", label: "Estimating Effort",      icon: Timer },
  { id: "critic", label: "Critic Validation",      icon: ShieldCheck },
  { id: "sprint", label: "Building Sprint Plan",   icon: Calendar },
  { id: "risk",   label: "Analyzing Risks",        icon: AlertTriangle },
];

function detectStage(log: string): string | null {
  const l = log.toLowerCase();
  if (l.includes("pars") || l.includes("brief")) return "parse";
  if (l.includes("plan") || l.includes("llm") || l.includes("task")) return "plan";
  if (l.includes("effort") || l.includes("estim") || l.includes("hour")) return "effort";
  if (l.includes("critic") || l.includes("valid")) return "critic";
  if (l.includes("sprint")) return "sprint";
  if (l.includes("risk")) return "risk";
  return null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

type PipelineEvent = { message?: string; data?: { task_count?: number; elapsed_seconds?: number } };
type ProgressSummary = {
  by_task?: Record<string, { status?: string; updated_at?: string } | string>;
};

function parseEvent(event: MessageEvent<string>): PipelineEvent {
  try { return JSON.parse(event.data) as PipelineEvent; } catch { return { message: event.data }; }
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

function riskColor(level: string) {
  const key = level.toLowerCase();
  if (key === "critical") return "#ef4444";
  if (key === "high") return "#f97316";
  if (key === "medium") return "#eab308";
  if (key === "low") return "#22c55e";
  return "#7dd3fc";
}

// ── Step indicator ───────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: "input" | "analyzing" | "results" }) {
  const steps = [
    { key: "input",     label: "Tell us" },
    { key: "analyzing", label: "Analyzing" },
    { key: "results",   label: "Ready!" },
  ] as const;
  const idx = steps.findIndex((s) => s.key === current);

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 0, marginBottom: 36 }}>
      {steps.map((step, i) => {
        const done = i < idx;
        const active = i === idx;
        const color = done ? "#22c55e" : active ? "#0284c7" : "#334155";
        return (
          <React.Fragment key={step.key}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
              <div
                style={{
                  width: 32, height: 32, borderRadius: "50%",
                  background: done ? "#22c55e" : active ? "#0284c7" : "#1e293b",
                  border: `2px solid ${color}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: 800, fontSize: 13, color: done || active ? "#fff" : "#475569",
                  transition: "all 0.3s",
                }}
              >
                {done ? "OK" : i + 1}
              </div>
              <span style={{ fontSize: 11, fontWeight: 600, color, whiteSpace: "nowrap" }}>
                {step.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div style={{ width: 80, height: 2, background: i < idx ? "#22c55e" : "#1e293b", margin: "0 4px", marginBottom: 18, transition: "all 0.3s" }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function StudentWorkspace() {
  const navigate = useNavigate();
  const logout = useAppStore((s) => s.logout);
  const resetWorkspace = useAppStore((s) => s.resetWorkspace);
  const auth = useAppStore((s) => s.auth);
  const data = useAppStore((s) => s.data);
  const brief = useAppStore((s) => s.brief);
  const refreshAll = useAppStore((s) => s.refreshAll);
  const refreshBrief = useAppStore((s) => s.refreshBrief);
  const liveTasks = useAppStore((s) => s.data?.tasks?.tasks);
  const riskLevel = useAppStore((s) => s.data?.risks?.risk_level ?? DEMO_ALL_DATA.risks?.risk_level ?? "unknown");
  const riskCount = useAppStore((s) => s.data?.risks?.total_risks ?? DEMO_ALL_DATA.risks?.total_risks ?? 0);
  const techStack = useAppStore((s) => s.data?.tasks?.tech_stack ?? DEMO_ALL_DATA.tasks?.tech_stack ?? null);
  const sprintPlanData = useAppStore((s) => s.data?.summary?.sprint_plan);
  const criticScore = useAppStore((s) => s.data?.summary?.critic?.score ?? DEMO_ALL_DATA.summary?.critic?.score ?? null);

  // wizard state
  type WizardStep = "input" | "analyzing" | "results";
  const [step, setStep] = useState<WizardStep>("input");

  // input step
  const [requirements, setRequirements] = useState(DEFAULT_PROJECT_BRIEF);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const hasEditedRequirements = useRef(false);

  // analyzing step
  const [lastLog, setLastLog] = useState("");
  const [currentStageId, setCurrentStageId] = useState<string | null>(null);
  const [doneStages, setDoneStages] = useState<string[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  // results step
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [chatError, setChatError] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [planStatus, setPlanStatus] = useState("pending");
  const chatBottomRef = useRef<HTMLDivElement | null>(null);
  const chatSectionRef = useRef<HTMLDivElement | null>(null);
  const [, setIsRuleBasedMode] = useState(false);
  const [taskRatings, setTaskRatings] = useState<Record<string, number>>({});
  const [ratingLoading, setRatingLoading] = useState<string | null>(null);
  const [taskProgress, setTaskProgress] = useState<Record<string, string>>({});

  // explain popup
  const [explainTarget, setExplainTarget] = useState<{ contextType: "task" | "risk" | "critic"; itemId: string; title: string } | null>(null);

  async function refreshChat() {
    try {
      const data = await getChatMessages();
      setChatMessages(data.messages);
      setPlanStatus(data.plan_status);
    } catch { /* silent */ }
  }

  async function refreshProgress() {
    try {
      const response = await axios.get<ProgressSummary>(`${API_BASE_URL}/progress/summary`);
      const mapped = Object.fromEntries(
        Object.entries(response.data.by_task ?? {}).map(([taskId, value]) => [
          taskId,
          typeof value === "string" ? value : value?.status ?? "not_started",
        ]),
      );
      setTaskProgress(mapped);
    } catch { /* silent */ }
  }

  useEffect(() => {
    void refreshChat();
    void refreshProgress();
    const t = window.setInterval(() => void refreshChat(), 5000);
    return () => window.clearInterval(t);
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

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  useEffect(() => () => eventSourceRef.current?.close(), []);

  // Fallback: if all stages are done but SSE complete event was missed, force transition
  useEffect(() => {
    if (step !== "analyzing" || doneStages.length < STAGES.length) return;
    const t = setTimeout(() => {
      void refreshAll();
      void refreshBrief();
      void refreshProgress();
      eventSourceRef.current?.close();
      setStep("results");
    }, 2000);
    return () => clearTimeout(t);
  }, [doneStages.length, step]); // eslint-disable-line react-hooks/exhaustive-deps

  function attachEvents() {
    eventSourceRef.current?.close();
    const source = new EventSource(pipelineEventsUrl());
    eventSourceRef.current = source;

    const advance = (log: string) => {
      setLastLog(log);
      const detected = detectStage(log);
      if (detected) {
        setCurrentStageId((prev) => {
          if (prev && prev !== detected) setDoneStages((d) => [...d, prev]);
          return detected;
        });
      }
    };

    source.addEventListener("heartbeat", (ev) => {
      const payload = parseEvent(ev as MessageEvent<string>);
      advance(payload.message ?? "");
      if ((payload as { status?: string }).status === "completed") {
        setDoneStages(STAGES.map((s) => s.id));
        setCurrentStageId(null);
        void refreshAll();
        void refreshBrief();
        void refreshProgress();
        source.close();
        setTimeout(() => setStep("results"), 600);
      }
    });
    source.addEventListener("status", (ev) => advance(parseEvent(ev as MessageEvent<string>).message ?? ""));
    source.addEventListener("log", (ev) => {
      const msg = parseEvent(ev as MessageEvent<string>).message ?? "";
      advance(msg);
      if (msg.toLowerCase().includes("fallback") || msg.toLowerCase().includes("rule-based") || msg.toLowerCase().includes("ollama not")) {
        setIsRuleBasedMode(true);
      }
    });
    source.addEventListener("complete",  (ev) => {
      const payload = parseEvent(ev as MessageEvent<string>);
      setLastLog(payload.message ?? "Pipeline complete");
      setDoneStages(STAGES.map((s) => s.id));
      setCurrentStageId(null);
      void refreshAll();
      void refreshBrief();
      void refreshProgress();
      source.close();
      setTimeout(() => setStep("results"), 600);
    });
    source.addEventListener("error", (ev) => {
      const payload = parseEvent(ev as MessageEvent<string>);
      setPipelineError(payload.message ?? "Pipeline failed.");
      setStep("input");
      source.close();
    });
  }

  async function handleGenerate() {
    const text = requirements.trim();
    if (!text) { setPipelineError("Please describe your project first."); return; }
    setIsRuleBasedMode(false);
    setPipelineError(null);
    setLastLog("");
    setCurrentStageId(null);
    setDoneStages([]);
    setStep("analyzing");
    attachEvents();
    try {
      await runPipeline({ requirements: text, input_format: "brief", use_kb: true });
    } catch (err) {
      setPipelineError(err instanceof Error ? err.message : "Pipeline failed to start.");
      setStep("input");
      eventSourceRef.current?.close();
    }
  }

  async function handleSubmitToSupervisor() {
    try {
      await sendChatMessage("Student", "My plan is ready for your review. Please check the Supervisor Dashboard.");
      setChatOpen(true);
      await refreshChat();
      setTimeout(() => chatSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
    } catch { /* silent */ }
  }

  function openCommunicationPanel() {
    setChatOpen(true);
    setTimeout(() => chatSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  }

  async function handleChatSend() {
    const text = chatMessage.trim();
    if (!text) return;
    try {
      await sendChatMessage("Student", text);
      setChatMessage("");
      setChatError(null);
      await refreshChat();
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Failed to send message.");
    }
  }

  async function rateTask(taskId: string, rating: number) {
    setRatingLoading(taskId);
    try {
      await axios.post(`${API_BASE_URL}/feedback/task`, { task_id: taskId, rating });
      setTaskRatings((prev) => ({ ...prev, [taskId]: rating }));
    } catch { /* silent */ }
    finally { setRatingLoading(null); }
  }

  async function updateTaskProgress(taskId: string, status: "not_started" | "in_progress" | "completed") {
    try {
      await axios.post(`${API_BASE_URL}/progress/update`, { task_id: taskId, status });
      setTaskProgress((prev) => ({ ...prev, [taskId]: status }));
    } catch { /* silent */ }
  }

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  function handleStartOver() {
    eventSourceRef.current?.close();
    resetWorkspace();
    hasEditedRequirements.current = false;
    setRequirements(DEFAULT_PROJECT_BRIEF);
    setPipelineError(null);
    setLastLog("");
    setCurrentStageId(null);
    setDoneStages([]);
    setExpandedTask(null);
    setChatOpen(false);
    setChatMessage("");
    setChatError(null);
    setExplainTarget(null);
    setTaskRatings({});
    setTaskProgress({});
    setIsRuleBasedMode(false);
    setStep("input");
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  // ── RENDER: Step 1 ──────────────────────────────────────────────────────────
  if (step === "input") {
    return (
      <div style={{ minHeight: "100vh", background: "#0f172a", padding: "40px 24px" }}>
        {/* header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", maxWidth: 760, margin: "0 auto 40px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(2,132,199,0.2)", border: "1px solid #0284c744", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Sparkles size={18} color="#7dd3fc" />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "#f1f5f9" }}>AI Project Manager</div>
              <div style={{ fontSize: 11, color: "#64748b" }}>Committee-ready planning</div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 13, color: "#64748b" }}>User: {auth?.name}</span>
            <button onClick={handleLogout} style={{ background: "transparent", border: "1px solid #334155", borderRadius: 7, padding: "6px 10px", cursor: "pointer", color: "#64748b", display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
              <LogOut size={13} /> Sign Out
            </button>
          </div>
        </div>

        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <StepIndicator current="input" />

          <div style={{ background: "rgba(15,23,42,0.97)", border: "1px solid #1e293b", borderRadius: 20, padding: "36px 32px" }}>
            <h1 style={{ fontSize: 24, fontWeight: 900, color: "#f1f5f9", margin: "0 0 8px" }}>
              Tell me about your project
            </h1>
            <p style={{ color: "#64748b", margin: "0 0 24px", fontSize: 14, lineHeight: 1.6 }}>
              Describe what you want to build. The AI will create a complete execution plan with tasks, sprints, and risk analysis.
            </p>

            {/* chips */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
              <span style={{ fontSize: 12, color: "#475569", alignSelf: "center" }}>Examples:</span>
              {Object.keys(SAMPLES).map((name) => (
                <button
                  key={name}
                  onClick={() => {
                    hasEditedRequirements.current = true;
                    setRequirements(SAMPLES[name]);
                  }}
                  style={{
                    background: requirements === SAMPLES[name] ? "rgba(2,132,199,0.2)" : "rgba(255,255,255,0.04)",
                    border: `1px solid ${requirements === SAMPLES[name] ? "#0284c766" : "#334155"}`,
                    borderRadius: 999,
                    padding: "5px 14px",
                    fontSize: 12,
                    color: requirements === SAMPLES[name] ? "#93c5fd" : "#7dd3fc",
                    cursor: "pointer",
                    transition: "all 0.2s",
                  }}
                >
                  {name}
                </button>
              ))}
            </div>

            <textarea
              rows={12}
              value={requirements}
              onChange={(e) => {
                hasEditedRequirements.current = true;
                setRequirements(e.target.value);
              }}
              style={{
                width: "100%",
                background: "#0a1120",
                border: "1px solid #334155",
                borderRadius: 12,
                color: "#f1f5f9",
                padding: "14px 16px",
                fontSize: 13,
                lineHeight: 1.7,
                resize: "vertical",
                fontFamily: "inherit",
                boxSizing: "border-box",
              }}
            />

            {pipelineError && (
              <div style={{ background: "#450a0a", border: "1px solid #7f1d1d", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#fca5a5", marginTop: 12 }}>
                {pipelineError}
              </div>
            )}

            <button
              onClick={() => void handleGenerate()}
              style={{
                marginTop: 20,
                width: "100%",
                padding: "14px 0",
                borderRadius: 12,
                border: "none",
                cursor: "pointer",
                fontWeight: 800,
                fontSize: 15,
                background: "linear-gradient(135deg, #0284c7, #1e40af)",
                color: "#fff",
                letterSpacing: "0.01em",
              }}
            >
              Generate My Plan -&gt;
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── RENDER: Step 2 ──────────────────────────────────────────────────────────
  if (step === "analyzing") {
    return (
      <div style={{ minHeight: "100vh", background: "#0f172a", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 40 }}>
        <div style={{ maxWidth: 520, width: "100%" }}>
          <StepIndicator current="analyzing" />

          <div style={{ background: "rgba(15,23,42,0.97)", border: "1px solid #1e293b", borderRadius: 20, padding: "40px 36px", textAlign: "center" }}>
            {/* spinner */}
            <div style={{ width: 56, height: 56, borderRadius: "50%", border: "3px solid #1e293b", borderTop: "3px solid #0284c7", margin: "0 auto 24px", animation: "spin 1s linear infinite" }} />
            <h2 style={{ fontSize: 20, fontWeight: 800, color: "#f1f5f9", margin: "0 0 6px" }}>AI Analysis in Progress</h2>
            <p style={{ color: "#64748b", margin: "0 0 32px", fontSize: 13 }}>Generating your project plan...</p>

            {/* stage list */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12, textAlign: "left", marginBottom: 28 }}>
              {STAGES.map((stage) => {
                const done = doneStages.includes(stage.id);
                const active = currentStageId === stage.id;
                const Icon = stage.icon;
                return (
                  <div key={stage.id} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div
                      style={{
                        width: 32, height: 32, borderRadius: "50%",
                        background: done ? "rgba(34,197,94,0.15)" : active ? "rgba(2,132,199,0.15)" : "rgba(255,255,255,0.03)",
                        border: `2px solid ${done ? "#22c55e" : active ? "#0284c7" : "#1e293b"}`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        flexShrink: 0, transition: "all 0.3s",
                      }}
                    >
                      {done
                        ? <span style={{ color: "#22c55e", fontSize: 14, fontWeight: 800 }}>OK</span>
                        : <Icon size={15} color={active ? "#7dd3fc" : "#475569"} />}
                    </div>
                    <span style={{ fontSize: 14, fontWeight: 600, color: done ? "#22c55e" : active ? "#f1f5f9" : "#475569", transition: "all 0.3s" }}>
                      {stage.label}
                    </span>
                    {active && (
                      <div style={{ marginLeft: "auto", width: 8, height: 8, borderRadius: "50%", background: "#0284c7", animation: "pulse 1.2s ease-in-out infinite" }} />
                    )}
                  </div>
                );
              })}
            </div>

            {lastLog && (
              <div style={{ background: "#0a1120", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#475569", textAlign: "left", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                &gt; {lastLog}
              </div>
            )}
          </div>
        </div>

        <style>{`
          @keyframes spin { to { transform: rotate(360deg); } }
          @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        `}</style>
      </div>
    );
  }

  // ── RENDER: Step 3 ──────────────────────────────────────────────────────────
  const rawTasks = Array.isArray(liveTasks) && liveTasks.length ? liveTasks : DEMO_ALL_DATA.tasks?.tasks ?? [];
  const tasks = buildPresentationTasks(rawTasks);
  const rawSprintPlan = Array.isArray(sprintPlanData) && sprintPlanData.length
    ? sprintPlanData
    : DEMO_ALL_DATA.summary?.sprint_plan ?? [];
  const sprintPlan = buildPresentationSprints(rawSprintPlan, rawTasks);
  const totalHours = tasks.reduce((sum, t) => sum + numberValue(t.estimated_hours), 0);
  const showcase = buildShowcaseData(data, brief);
  const committeeSprintPlan = sortPresentationSprints(sprintPlan);
  const riskAccent = riskColor(riskLevel);
  const sprintCount = sprintPlan.length;
  const totalCount = tasks.length;
  const completedCount = tasks.filter((task) => task.id && taskProgress[task.id] === "completed").length;
  const progressPercentage = totalCount ? Math.round((completedCount / totalCount) * 100) : 0;
  const qualityGateLabel = formatQualityGate(criticScore);
  const trackingTitle = completedCount > 0 ? "Implementation Tracking" : "Implementation Baseline";
  const trackingSummary = completedCount > 0
    ? `${completedCount}/${totalCount} tasks completed`
    : `${totalCount} tasks ready for execution`;
  const showSupervisorChat = true;

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", padding: "32px 24px 64px" }}>
      {/* header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", maxWidth: 960, margin: "0 auto 32px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(2,132,199,0.2)", border: "1px solid #0284c744", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Sparkles size={18} color="#7dd3fc" />
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: "#f1f5f9" }}>AI Project Manager</div>
            <div style={{ fontSize: 11, color: "#64748b" }}>Committee-ready planning</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            onClick={handleStartOver}
            style={{ background: "transparent", border: "1px solid #334155", borderRadius: 7, padding: "7px 12px", cursor: "pointer", color: "#64748b", fontSize: 12 }}
          >
            <RefreshCw size={13} style={{ display: "inline", marginRight: 5 }} />
            Start Over
          </button>
          <button onClick={handleLogout} style={{ background: "transparent", border: "1px solid #334155", borderRadius: 7, padding: "7px 10px", cursor: "pointer", color: "#64748b", display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
            <LogOut size={13} /> Sign Out
          </button>
        </div>
      </div>

      <div style={{ maxWidth: 960, margin: "0 auto" }}>
        <StepIndicator current="results" />

        {/* success banner */}
        <div style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.25)", borderRadius: 14, padding: "14px 20px", display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <CheckCircle size={20} color="#22c55e" />
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#22c55e" }}>AI Analysis Complete</div>
            <div style={{ fontSize: 12, color: "#64748b" }}>Your project plan is ready, and the supervisor communication channel stays open during review and sign-off.</div>
          </div>
          <button
            onClick={openCommunicationPanel}
            style={{ background: "transparent", border: "1px solid #334155", borderRadius: 9, padding: "9px 14px", cursor: "pointer", color: "#cbd5e1", fontWeight: 700, fontSize: 13, whiteSpace: "nowrap" }}
          >
            Open Communication
          </button>
          <button
            onClick={() => void handleSubmitToSupervisor()}
            style={{ marginLeft: "auto", background: "linear-gradient(135deg,#475569,#334155)", border: "none", borderRadius: 9, padding: "9px 18px", cursor: "pointer", color: "#fff", fontWeight: 700, fontSize: 13, whiteSpace: "nowrap" }}
          >
            Submit to Supervisor -&gt;
          </button>
        </div>

        <ProjectShowcase showcase={showcase} />

        {/* metric cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 24 }}>
          {[
            { label: "Tasks", value: tasks.length, color: "#3b82f6", Icon: ListChecks },
            { label: "Total Hours", value: `${totalHours}h`, color: "#14b8a6", Icon: Timer },
            { label: "Sprints", value: sprintCount || "n/a", color: "#475569", Icon: Calendar },
            { label: "Quality Gate", value: criticScore != null ? qualityGateLabel : `${riskCount} risks`, color: criticScore != null ? "#22c55e" : riskAccent || "#ef4444", Icon: criticScore != null ? CheckCircle : ShieldAlert },
          ].map(({ label, value, color, Icon }) => (
            <div key={label} style={{ background: "rgba(15,23,42,0.97)", border: "1px solid #1e293b", borderRadius: 16, padding: "18px 20px", borderTop: `2px solid ${color}` }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: `${color}22`, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 10 }}>
                <Icon size={18} color={color} />
              </div>
              <div style={{ fontSize: 26, fontWeight: 900, color: "#f8fafc" }}>{value}</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 6 }}>{label}</div>
            </div>
          ))}
        </div>

        <div style={{ background: "#0f1e35", border: "1px solid #1e293b", borderRadius: 10, padding: "12px 16px", marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 12, color: "#64748b" }}>{trackingTitle}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#f1f5f9" }}>{trackingSummary}</span>
          </div>
          <div style={{ height: 6, background: "#1e293b", borderRadius: 99 }}>
            <div style={{ height: "100%", width: `${progressPercentage}%`, background: "linear-gradient(90deg, #0284c7, #22c55e)", borderRadius: 99, transition: "width 0.5s" }} />
          </div>
        </div>

        {/* tech stack */}
        {techStack && (["frontend", "backend", "database", "devops", "external_services"] as const).some((cat) => techStack[cat]?.length > 0) && (
          <div style={{ background: "rgba(15,23,42,0.97)", border: "1px solid #1e293b", borderRadius: 12, padding: "16px 20px", marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 12 }}>
              Detected Tech Stack
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {(["frontend", "backend", "database", "devops", "external_services"] as const).flatMap((cat) =>
                (techStack[cat] ?? []).map((tech) => {
                  const colors: Record<string, { bg: string; fg: string }> = {
                    frontend:          { bg: "rgba(2,132,199,0.15)",   fg: "#93c5fd" },
                    backend:           { bg: "rgba(124,58,237,0.15)",  fg: "#c4b5fd" },
                    database:          { bg: "rgba(8,145,178,0.15)",   fg: "#67e8f9" },
                    devops:            { bg: "rgba(234,179,8,0.15)",   fg: "#fde68a" },
                    external_services: { bg: "rgba(34,197,94,0.15)",   fg: "#86efac" },
                  };
                  const { bg, fg } = colors[cat];
                  return (
                    <span
                      key={`${cat}-${tech}`}
                      style={{
                        background: bg, color: fg,
                        border: "1px solid currentColor",
                        borderRadius: 999, padding: "3px 10px",
                        fontSize: 12, fontWeight: 600, opacity: 0.85,
                      }}
                    >
                      {tech}
                    </span>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* sprint summary */}
        {committeeSprintPlan.length > 0 && (
          <div style={{ background: "rgba(15,23,42,0.97)", border: "1px solid #1e293b", borderRadius: 16, padding: 20, marginBottom: 24 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 14 }}>Delivery Storyline</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {committeeSprintPlan.map((sp) => (
                <div key={`${sp.sprint}-${sp.displayName}`} style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", background: "#0a1120", border: "1px solid #1e293b", borderRadius: 10 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: "rgba(2,132,199,0.15)", border: "1px solid #0284c733", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 900, fontSize: 13, color: "#7dd3fc", flexShrink: 0 }}>
                    {sp.displaySprint}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, color: "#f1f5f9", fontSize: 14 }}>{sp.displayName ?? sp.name ?? `Sprint ${sp.sprint}`}</div>
                    {(sp.displayGoal ?? sp.goal) && <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>{sp.displayGoal ?? sp.goal}</div>}
                  </div>
                  <div style={{ display: "flex", gap: 16, fontSize: 12, color: "#64748b" }}>
                    <span><strong style={{ color: "#7dd3fc" }}>{sp.tasks?.length ?? 0}</strong> tasks</span>
                    <span><strong style={{ color: "#7dd3fc" }}>{sp.duration_weeks ?? "?"}</strong>w</span>
                    <span><strong style={{ color: "#7dd3fc" }}>{sp.total_estimated_hours ?? 0}</strong>h</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* task list */}
        <div style={{ background: "rgba(15,23,42,0.97)", border: "1px solid #1e293b", borderRadius: 16, padding: 20, marginBottom: 24 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 14 }}>
            Generated Tasks ({tasks.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {tasks.map((task) => {
              const id = task.id ?? task.title ?? "";
              const taskId = task.id ?? "";
              const isExpanded = expandedTask === id;
              const color = complexityColor(task.complexity);

              return (
                <div
                  key={id}
                  style={{ border: "1px solid #1e293b", borderRadius: 12, background: "#0a1120", overflow: "hidden" }}
                >
                  <div
                    onClick={() => setExpandedTask(isExpanded ? null : id)}
                    style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", cursor: "pointer" }}
                  >
                    <span style={{ fontFamily: "monospace", background: "rgba(59,130,246,0.14)", color: "#93c5fd", padding: "4px 8px", borderRadius: 6, fontWeight: 800, fontSize: 12, flexShrink: 0 }}>
                      {task.id}
                    </span>
                    <div style={{ flex: 1, fontWeight: 600, color: "#f1f5f9", fontSize: 14 }}>{task.title}</div>
                    <span className={`badge ${task.req_type === "NFR" ? "badge-orange" : "badge-blue"}`} style={{ flexShrink: 0 }}>{task.req_type}</span>
                    <span style={{ borderRadius: 999, padding: "3px 8px", background: `${color}22`, color, fontWeight: 800, fontSize: 12, flexShrink: 0 }}>C{task.complexity}</span>
                    <span style={{ color: "#7dd3fc", fontWeight: 700, fontSize: 13, flexShrink: 0 }}>{task.estimated_hours ?? 0}h</span>
                    <div style={{ display: "flex", gap: 4 }} onClick={(e) => e.stopPropagation()}>
                      {(["not_started", "in_progress", "completed"] as const).map((statusKey) => {
                        const active = task.id ? taskProgress[task.id] === statusKey : false;
                        return (
                          <button
                            key={statusKey}
                            onClick={() => task.id && void updateTaskProgress(task.id, statusKey)}
                            style={{
                              fontSize: 10,
                              padding: "2px 8px",
                              borderRadius: 999,
                              border: "1px solid",
                              background: active
                                ? statusKey === "completed"
                                  ? "rgba(34,197,94,0.2)"
                                  : statusKey === "in_progress"
                                  ? "rgba(59,130,246,0.2)"
                                  : "rgba(2,132,199,0.2)"
                                : "transparent",
                              color: active
                                ? statusKey === "completed"
                                  ? "#4ade80"
                                  : statusKey === "in_progress"
                                  ? "#7dd3fc"
                                  : "#7dd3fc"
                                : "#334155",
                              borderColor: "currentColor",
                              cursor: task.id ? "pointer" : "default",
                            }}
                          >
                            {statusKey === "not_started" ? "Todo" : statusKey === "in_progress" ? "Doing" : "Done"}
                          </button>
                        );
                      })}
                    </div>
                    {isExpanded ? <ChevronUp size={15} color="#475569" /> : <ChevronDown size={15} color="#475569" />}
                  </div>

                  {isExpanded && (
                    <div style={{ padding: "0 16px 16px", borderTop: "1px solid #1e293b" }}>
                      <div style={{ height: 4, background: "#1e293b", borderRadius: 99, overflow: "hidden", marginTop: 12 }}>
                        <div style={{ height: "100%", width: `${(Math.max(1, numberValue(task.complexity)) / 5) * 100}%`, background: complexityColor(task.complexity), borderRadius: 99, transition: "width 0.3s" }} />
                      </div>
                      <div style={{ paddingTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 12 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Details</div>
                          <div style={{ fontSize: 13, color: "#7dd3fc", lineHeight: 1.5, marginBottom: 8 }}>{task.description ?? "n/a"}</div>
                          <div style={{ fontSize: 12, color: "#64748b" }}>Owner: <strong style={{ color: "#7dd3fc" }}>{task.suggested_owner_role ?? task.skill_required ?? "N/A"}</strong></div>
                          <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                            <div style={{ background: "rgba(100,116,139,0.08)", border: "1px solid rgba(100,116,139,0.18)", borderRadius: 8, padding: "8px 10px" }}>
                              <div style={{ fontSize: 10, fontWeight: 700, color: "#7dd3fc", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Type Reason</div>
                              <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.6 }}>{task.type_reason ?? "Describes a user-facing feature or quality requirement inferred by the planner."}</div>
                            </div>
                            <div style={{ background: "rgba(20,184,166,0.08)", border: "1px solid rgba(20,184,166,0.18)", borderRadius: 8, padding: "8px 10px" }}>
                              <div style={{ fontSize: 10, fontWeight: 700, color: "#2dd4bf", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Complexity Reason</div>
                              <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.6 }}>{task.complexity_reason ?? "Estimated from implementation scope, coordination, and integration needs."}</div>
                            </div>
                          </div>
                          {task.dependencies?.length ? (
                            <div style={{ marginTop: 8, fontSize: 12, color: "#64748b" }}>
                              Depends on: {task.dependencies.map((d) => (
                                <span key={d} style={{ fontFamily: "monospace", background: "rgba(255,255,255,0.05)", color: "#7dd3fc", padding: "2px 6px", borderRadius: 4, marginLeft: 4 }}>{d}</span>
                              ))}
                            </div>
                          ) : null}
                        </div>

                        <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 12 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Effort Breakdown</div>
                          {[
                            ["Estimated Hours", `${task.estimated_hours ?? 0}h`],
                            ["Estimated Days", `${task.estimated_days ?? "?"}d`],
                            ["Team Size", `${task.recommended_team_size ?? 1} person(s)`],
                            ["Skill Required", task.skill_required ?? "N/A"],
                          ].map(([lbl, val]) => (
                            <div key={lbl} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid #1e293b", fontSize: 12 }}>
                              <span style={{ color: "#64748b" }}>{lbl}</span>
                              <strong style={{ color: "#7dd3fc" }}>{val}</strong>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Ask AI button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setExplainTarget({ contextType: "task", itemId: task.id ?? "", title: task.title ?? "" });
                        }}
                        style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 6, background: "rgba(100,116,139,0.12)", border: "1px solid rgba(100,116,139,0.3)", borderRadius: 8, padding: "8px 14px", cursor: "pointer", color: "#93c5fd", fontSize: 13, fontWeight: 600 }}
                      >
                        <Sparkles size={14} color="#7dd3fc" />
                        Ask AI: Why was this task created?
                      </button>
                      {task.id && (
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
                          <span style={{ fontSize: 12, color: "#64748b" }}>Rate this task:</span>
                          {[1, 2, 3, 4, 5].map((star) => (
                            <button
                              key={star}
                              onClick={() => void rateTask(taskId, star)}
                              disabled={ratingLoading === task.id}
                              style={{
                                background: "none",
                                border: "none",
                                cursor: ratingLoading === task.id ? "wait" : "pointer",
                                padding: 2,
                                color: (taskRatings[taskId] ?? 0) >= star ? "#fbbf24" : "#334155",
                                fontSize: 18,
                                transition: "color 0.15s",
                                display: "flex",
                                alignItems: "center",
                              }}
                            >
                              <Star size={17} fill={(taskRatings[taskId] ?? 0) >= star ? "#fbbf24" : "transparent"} />
                            </button>
                          ))}
                          {taskRatings[taskId] && (
                            <span style={{ fontSize: 11, color: "#64748b" }}>Saved</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* chat section (collapsible) */}
        {showSupervisorChat && (
        <div ref={chatSectionRef} style={{ background: "rgba(15,23,42,0.97)", border: "1px solid #1e293b", borderRadius: 16, overflow: "hidden" }}>
          <button
            onClick={() => setChatOpen((o) => !o)}
            style={{ width: "100%", background: "transparent", border: "none", padding: "14px 20px", display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
          >
            <MessageSquare size={16} color="#7dd3fc" />
            <span style={{ fontWeight: 700, fontSize: 14, color: "#f1f5f9" }}>Communication With Supervisor</span>
            <span style={{
              marginLeft: 8, fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
              background: planStatus === "approved" ? "rgba(34,197,94,0.15)" : planStatus === "rejected" ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)",
              color: planStatus === "approved" ? "#4ade80" : planStatus === "rejected" ? "#f87171" : "#7dd3fc",
            }}>
              {planStatus.toUpperCase()}
            </span>
            <span style={{ marginLeft: "auto", color: "#475569" }}>{chatOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</span>
          </button>

          {chatOpen && (
            <>
              <div style={{ borderTop: "1px solid #1e293b", height: 300, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
                {chatMessages.length ? chatMessages.map((msg) => {
                  if (msg.type === "approval" || msg.type === "rejection") {
                    const approved = msg.type === "approval";
                    return (
                      <div key={msg.id} style={{ display: "flex", justifyContent: "center" }}>
                        <div style={{ background: approved ? "rgba(34,197,94,0.16)" : "rgba(239,68,68,0.16)", color: approved ? "#4ade80" : "#f87171", border: `1px solid ${approved ? "rgba(34,197,94,0.24)" : "rgba(239,68,68,0.24)"}`, borderRadius: 999, padding: "8px 14px", fontSize: 13, fontWeight: 700 }}>
                          {approved ? "Plan Approved" : "Plan Rejected"}
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div key={msg.id} style={{ display: "flex", justifyContent: msg.role === "Student" ? "flex-end" : "flex-start" }}>
                      <div style={{ maxWidth: "80%", background: msg.role === "Student" ? "#334155" : "#1e293b", border: msg.role === "Supervisor" ? "1px solid #334155" : "none", borderRadius: msg.role === "Student" ? "14px 14px 2px 14px" : "14px 14px 14px 2px", padding: "8px 12px" }}>
                        <div style={{ fontSize: 10, color: "#64748b", marginBottom: 3 }}>{msg.role} | {new Date(msg.created_at).toLocaleTimeString()}</div>
                        <div style={{ color: "#f1f5f9", fontSize: 13, lineHeight: 1.5 }}>{msg.text}</div>
                      </div>
                    </div>
                  );
                }) : (
                  <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8, opacity: 0.4 }}>
                    <MessageSquare size={36} color="#64748b" />
                    <span style={{ color: "#64748b", fontSize: 13, textAlign: "center", maxWidth: 420 }}>No messages yet. Use this channel to submit the plan, ask questions, and receive supervisor approval or revision notes.</span>
                  </div>
                )}
                <div ref={chatBottomRef} />
              </div>
              <div style={{ borderTop: "1px solid #1e293b", padding: "10px 12px", display: "flex", gap: 8 }}>
                <textarea
                  rows={2}
                  value={chatMessage}
                  onChange={(e) => setChatMessage(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void handleChatSend(); } }}
                  placeholder="Write a message to your supervisor..."
                  style={{ flex: 1, background: "#020617", border: "1px solid #334155", borderRadius: 8, color: "#f8fafc", padding: "8px 10px", fontSize: 12, resize: "none", fontFamily: "inherit" }}
                />
                <button onClick={() => void handleChatSend()} style={{ background: "#0284c7", border: "none", borderRadius: 8, padding: "0 14px", cursor: "pointer", color: "#fff" }}>
                  <Send size={15} />
                </button>
              </div>
              {chatError && (
                <div style={{ color: "#f87171", fontSize: 12, marginTop: 6, padding: "0 12px 12px" }}>{chatError}</div>
              )}
            </>
          )}
        </div>
        )}
      </div>

      {/* explain popup */}
      {explainTarget && (
        <ExplainPopup
          isOpen={!!explainTarget}
          onClose={() => setExplainTarget(null)}
          contextType={explainTarget.contextType}
          itemId={explainTarget.itemId}
          itemTitle={explainTarget.title}
        />
      )}
    </div>
  );
}

