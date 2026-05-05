import { useState } from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";

import { useAppStore } from "../lib/store";

const CATEGORY_LABELS: Record<string, string> = {
  bottleneck: "Dependency bottleneck detected",
  schedule: "Schedule pressure",
  dependency: "Dependency chain risk",
  resource: "Resource concentration",
  complexity: "Complexity spike",
  quality: "Quality signal",
};

const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;

const SEVERITY_META: Record<string, { color: string; icon: string; label: string }> = {
  critical: { color: "#ef4444", icon: "🔴", label: "Critical" },
  high: { color: "#f97316", icon: "🟠", label: "High" },
  medium: { color: "#eab308", icon: "🟡", label: "Medium" },
  low: { color: "#4ade80", icon: "🟢", label: "Low" },
};

function levelMeta(level: string) {
  const key = level.toLowerCase();
  if (key === "critical") return { color: "#ef4444", bg: "rgba(239,68,68,0.16)", label: "CRITICAL" };
  if (key === "high") return { color: "#f97316", bg: "rgba(249,115,22,0.16)", label: "HIGH" };
  if (key === "medium") return { color: "#eab308", bg: "rgba(234,179,8,0.16)", label: "MEDIUM" };
  if (key === "low") return { color: "#4ade80", bg: "rgba(74,222,128,0.14)", label: "LOW" };
  return { color: "#94a3b8", bg: "rgba(148,163,184,0.12)", label: "UNKNOWN" };
}

function categoryLabel(category: string | undefined) {
  if (!category) return "Risk indicator";
  return CATEGORY_LABELS[category] ?? category;
}

export default function RisksPage() {
  const data = useAppStore(s => s.data);
  const risk = data?.risks;
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    critical: true,
    high: true,
    medium: true,
    low: true,
  });

  if (!risk) {
    return (
      <div style={{ padding: 60, textAlign: "center", color: "#475569" }}>
        <AlertTriangle size={48} style={{ margin: "0 auto 16px", opacity: 0.4 }} />
        <p style={{ fontSize: 16 }}>Run the pipeline first to see the risk indicators.</p>
      </div>
    );
  }

  const risks = risk.risks ?? [];
  const score = risk.risk_score ?? 0;
  const level = levelMeta(risk.risk_level ?? "unknown");
  const grouped = SEVERITY_ORDER.reduce((acc, severity) => {
    acc[severity] = risks.filter(item => item.severity === severity);
    return acc;
  }, {} as Record<typeof SEVERITY_ORDER[number], typeof risks>);

  return (
    <div className="fade-up">
      <h1 className="page-title"><AlertTriangle size={22} /> Risk Indicators</h1>
      <p className="page-sub">Rule-based early warning signals — not AI predictions</p>

      <section style={{
        background: "rgba(15,23,42,0.9)",
        border: "1px solid #1e293b",
        borderRadius: 16,
        padding: 22,
        marginBottom: 22,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 18, alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <span style={{
              display: "inline-flex",
              alignItems: "center",
              borderRadius: 999,
              padding: "8px 18px",
              background: level.bg,
              color: level.color,
              border: `1px solid ${level.color}`,
              fontSize: "1.4rem",
              fontWeight: 900,
            }}>
              {level.label}
            </span>
            <div style={{ marginTop: 12, color: "#94a3b8", fontSize: 14 }}>
              {risks.length} risk indicators detected
            </div>
          </div>
          <div style={{ flex: "1 1 340px", maxWidth: 640 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ color: "#64748b", fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                Risk Score
              </span>
              <span style={{ color: "#f8fafc", fontWeight: 900 }}>{Math.round(score * 100)}%</span>
            </div>
            <div style={{ height: 14, background: "#0a0f1e", borderRadius: 999, border: "1px solid #1e293b", overflow: "hidden" }}>
              <div style={{ width: `${Math.round(score * 100)}%`, height: "100%", background: level.color, borderRadius: 999 }} />
            </div>
          </div>
        </div>
      </section>

      {risks.length === 0 ? (
        <div style={{ textAlign: "center", padding: "70px 20px", color: "#4ade80" }}>
          <div style={{ fontSize: 54, marginBottom: 12 }}>✅</div>
          <ShieldCheck size={36} style={{ margin: "0 auto 10px" }} />
          <p style={{ fontSize: 18, fontWeight: 800 }}>No risk indicators detected</p>
        </div>
      ) : (
        SEVERITY_ORDER
          .filter(severity => grouped[severity].length > 0)
          .map(severity => {
            const meta = SEVERITY_META[severity];
            const isOpen = openGroups[severity] ?? true;
            return (
              <section key={severity} style={{ marginBottom: 18 }}>
                <button
                  onClick={() => setOpenGroups(current => ({ ...current, [severity]: !isOpen }))}
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
                    <span>{meta.icon}</span> {meta.label} ({grouped[severity].length})
                  </span>
                  <span style={{ color: "#64748b" }}>{isOpen ? "collapse" : "expand"}</span>
                </button>

                {isOpen && (
                  <div style={{ display: "grid", gap: 10 }}>
                    {grouped[severity].map((item, index) => {
                      const category = categoryLabel(item.category);
                      return (
                        <div key={`${severity}-${index}`} style={{
                          display: "flex",
                          background: "rgba(15,23,42,0.9)",
                          border: "1px solid #1e293b",
                          borderRadius: 14,
                          overflow: "hidden",
                        }}>
                          <div style={{ width: 4, background: meta.color, flexShrink: 0 }} />
                          <div style={{ padding: 16, flex: 1 }}>
                            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                              <span style={{ background: "rgba(255,255,255,0.06)", color: "#e2e8f0", borderRadius: 999, padding: "4px 9px", fontSize: 12, fontWeight: 800 }}>
                                {category}
                              </span>
                              <span style={{ background: `${meta.color}22`, color: meta.color, borderRadius: 999, padding: "4px 9px", fontSize: 12, fontWeight: 900 }}>
                                {item.severity}
                              </span>
                              <span style={{ color: "#64748b", fontSize: "0.75rem" }}>
                                Rule-based detection
                              </span>
                            </div>

                            <div style={{ marginTop: 8, color: "#f1f5f9", lineHeight: 1.5 }}>
                              {item.message}
                            </div>

                            {(item.affected_tasks ?? []).length > 0 && (
                              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                                {(item.affected_tasks ?? []).map(taskId => (
                                  <span key={taskId} style={{
                                    fontFamily: "monospace",
                                    background: "rgba(255,255,255,0.06)",
                                    color: "#cbd5e1",
                                    padding: "4px 7px",
                                    borderRadius: 7,
                                  }}>
                                    {taskId}
                                  </span>
                                ))}
                              </div>
                            )}

                            {item.mitigation ? (
                              <div style={{
                                marginTop: 12,
                                background: "rgba(74,222,128,0.08)",
                                borderLeft: "3px solid #4ade80",
                                padding: 10,
                                color: "#bbf7d0",
                                borderRadius: 8,
                              }}>
                                <strong style={{ color: "#4ade80" }}>💡 Suggested: </strong>{item.mitigation}
                              </div>
                            ) : null}
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
    </div>
  );
}
