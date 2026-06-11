import React from "react";
import { ArrowDown, BriefcaseBusiness, ShieldCheck, Sparkles, Waypoints } from "lucide-react";

import type { ShowcaseData } from "../lib/projectShowcase";

export default function ProjectShowcase({
  showcase,
  accent = "#0284c7",
}: {
  showcase: ShowcaseData;
  accent?: string;
}) {
  return (
    <section
      style={{
        background: "linear-gradient(135deg, rgba(2,132,199,0.12), rgba(15,23,42,0.96))",
        border: "1px solid rgba(59,130,246,0.22)",
        borderRadius: 18,
        padding: 22,
        marginBottom: 20,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap", marginBottom: 18 }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, borderRadius: 999, padding: "5px 11px", background: "rgba(125,211,252,0.08)", border: "1px solid rgba(125,211,252,0.16)", color: "#7dd3fc", fontSize: 12, fontWeight: 800, marginBottom: 10 }}>
            <Sparkles size={14} color="#7dd3fc" />
            {showcase.dataLabel}
          </div>
          <h2 style={{ margin: 0, fontSize: 26, color: "#f8fafc", fontWeight: 900 }}>{showcase.title}</h2>
          <p style={{ margin: "8px 0 0", color: "#cbd5e1", fontSize: 14, lineHeight: 1.7, maxWidth: 860 }}>
            {showcase.summary}
          </p>
        </div>
        <div style={{ display: "grid", gap: 8, minWidth: 220 }}>
          <div style={{ borderRadius: 14, border: "1px solid rgba(34,197,94,0.18)", background: "rgba(34,197,94,0.08)", padding: "12px 14px" }}>
            <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "#86efac", fontWeight: 800, marginBottom: 5 }}>
              Confidence
            </div>
            <div style={{ color: "#dcfce7", fontSize: 13, lineHeight: 1.6 }}>{showcase.confidence}</div>
          </div>
          <div style={{ borderRadius: 14, border: "1px solid rgba(59,130,246,0.18)", background: "rgba(59,130,246,0.08)", padding: "12px 14px" }}>
            <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "#93c5fd", fontWeight: 800, marginBottom: 5 }}>
              Delivery Cadence
            </div>
            <div style={{ color: "#dbeafe", fontSize: 13, lineHeight: 1.6 }}>{showcase.sprintLabel}</div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 14, marginBottom: 18 }}>
        {[
          { label: "Domain", value: showcase.domain, icon: BriefcaseBusiness, color: "#7dd3fc" },
          { label: "Scope", value: showcase.scope, icon: Waypoints, color: accent },
          { label: "Review Signal", value: showcase.confidence, icon: ShieldCheck, color: "#4ade80" },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} style={{ borderRadius: 16, border: "1px solid #1e293b", background: "rgba(2,6,23,0.42)", padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <div style={{ width: 34, height: 34, borderRadius: 10, background: `${color}22`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Icon size={18} color={color} />
              </div>
              <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800 }}>{label}</div>
            </div>
            <div style={{ color: "#f8fafc", fontSize: 14, lineHeight: 1.65 }}>{value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.35fr 1fr", gap: 16 }}>
        <div style={{ borderRadius: 16, border: "1px solid #1e293b", background: "rgba(2,6,23,0.42)", padding: 16 }}>
          <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 12 }}>
            Committee Walkthrough
          </div>
          <div style={{ color: "#64748b", fontSize: 12, lineHeight: 1.6, marginBottom: 12 }}>
            {showcase.criticalPathNote}
          </div>
          <div style={{ display: "grid", gap: 10 }}>
            {showcase.criticalPath.map((step, index) => (
              <React.Fragment key={step.id}>
                <div style={{ borderRadius: 12, border: "1px solid rgba(59,130,246,0.2)", background: "rgba(59,130,246,0.08)", padding: "12px 14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                    <div style={{ minWidth: 28, height: 28, borderRadius: 999, background: "rgba(147,197,253,0.12)", color: "#93c5fd", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 900 }}>
                      {index + 1}
                    </div>
                    <div style={{ color: "#93c5fd", fontFamily: "monospace", fontSize: 12, fontWeight: 800 }}>{step.id}</div>
                  </div>
                  <div style={{ color: "#f8fafc", fontSize: 13, lineHeight: 1.5 }}>{step.title}</div>
                </div>
                {index < showcase.criticalPath.length - 1 && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 8, color: "#475569", fontSize: 12 }}>
                    <ArrowDown size={16} color="#475569" />
                    Next milestone
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gap: 16 }}>
          <div style={{ borderRadius: 16, border: "1px solid #1e293b", background: "rgba(2,6,23,0.42)", padding: 16 }}>
            <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 10 }}>
              Committee Talking Points
            </div>
            <div style={{ display: "grid", gap: 8 }}>
              {showcase.evidence.map((point) => (
                <div key={point} style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.6 }}>
                  {point}
                </div>
              ))}
            </div>
          </div>

          <div style={{ borderRadius: 16, border: "1px solid #1e293b", background: "rgba(2,6,23,0.42)", padding: 16 }}>
            <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 10 }}>
              Execution Ownership
            </div>
            <div style={{ display: "grid", gap: 8 }}>
              {showcase.teamRoles.map((role) => (
                <div key={role} style={{ color: "#e2e8f0", fontSize: 13, lineHeight: 1.55 }}>
                  {role}
                </div>
              ))}
            </div>
            <div style={{ height: 1, background: "#1e293b", margin: "14px 0" }} />
            <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "#64748b", fontWeight: 800, marginBottom: 10 }}>
              Main Risk Themes
            </div>
            <div style={{ display: "grid", gap: 8 }}>
              {showcase.riskFocus.map((risk) => (
                <div key={risk} style={{ color: "#fcd34d", fontSize: 13, lineHeight: 1.55 }}>
                  {risk}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
