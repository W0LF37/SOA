import { useEffect, useState } from "react";
import { Printer, Sparkles } from "lucide-react";
import { getBrief, type BriefData } from "../lib/api";

function ScoreBadge({ score }: { score?: number }) {
  if (score == null) return null;
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? "text-green-400" : pct >= 60 ? "text-yellow-400" : "text-red-400";
  return <span className={`font-bold ${color}`}>{pct}%</span>;
}

function SectionHeader({ icon, title }: { icon: string; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <span className="text-xl">{icon}</span>
      <h2 className="text-lg font-bold text-white">{title}</h2>
    </div>
  );
}

export default function BriefPage() {
  const [brief, setBrief] = useState<BriefData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getBrief()
      .then(setBrief)
      .catch(() => setError("No brief available. Run the pipeline first."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="animate-spin text-3xl mr-3">⚙</div>
        <span>Loading committee brief…</span>
      </div>
    );
  }

  if (error || !brief) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-gray-400">
        <div className="text-5xl">📄</div>
        <p className="text-lg font-medium">{error || "No brief data available"}</p>
        <p className="text-sm">Run the pipeline from the Plan page first.</p>
      </div>
    );
  }

  const cb = brief.committee_brief || {};
  const effort = brief.effort_summary || {};
  const team = brief.team_allocation || [];
  const risks = brief.risk_register || [];
  const ambiguity = cb.ambiguity_register || [];
  const assumptions = cb.assumption_log || [];
  const coverDate = new Date(brief.generated_at ?? Date.now()).toLocaleDateString();

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="brief-cover-page">
        <div style={{ display: "flex", justifyContent: "center" }}>
          <Sparkles size={32} color="#2563eb" />
        </div>
        <h1 className="brief-cover-title">Project Planning Committee Brief</h1>
        <p className="brief-cover-subtitle">AI-Generated Execution Plan</p>
        <div className="brief-cover-meta">
          <span>Generated: {coverDate}</span>
          <span>Model: {brief.model ?? "ai-project-manager-planner"}</span>
          <span>Powered by CritiPlan · Local AI (Ollama)</span>
        </div>
        <div className="brief-cover-stamp">AI GENERATED — ACADEMIC USE</div>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Committee Brief</h1>
        <div className="flex items-center gap-3">
          {brief.generated_at && (
            <span className="text-xs text-gray-500">
              {new Date(brief.generated_at).toLocaleDateString()}
            </span>
          )}
          {brief.generation_mode && (
            <span className="text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded-full">
              {brief.generation_mode.replace(/_/g, " ")}
            </span>
          )}
          {brief.critic?.score != null && (
            <span className="text-xs bg-gray-700 px-2 py-1 rounded-full">
              Critic: <ScoreBadge score={brief.critic.score} />
            </span>
          )}
          <button
            onClick={() => window.print()}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              padding: "7px 14px",
              cursor: "pointer",
              color: "#94a3b8",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            <Printer size={14} /> Export as PDF
          </button>
        </div>
      </div>

      {/* Executive Summary */}
      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
        <SectionHeader icon="🎯" title="Executive Summary" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div className="bg-gray-700 rounded-lg p-4">
            <p className="text-xs text-gray-400 mb-1">Domain</p>
            <p className="text-sm text-white font-medium">{cb.domain_inference || "—"}</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <p className="text-xs text-gray-400 mb-1">Scope</p>
            <p className="text-sm text-white font-medium">{cb.scope_assessment || "—"}</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <p className="text-xs text-gray-400 mb-1">Confidence</p>
            <p className="text-sm text-white font-medium">{cb.confidence_signal || "—"}</p>
          </div>
        </div>

        {/* Effort summary */}
        {effort.total_estimated_hours > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            <div className="bg-blue-900/40 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-blue-300">{effort.total_estimated_hours}h</div>
              <div className="text-xs text-gray-400">Total Hours</div>
            </div>
            <div className="bg-green-900/40 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-green-300">{effort.total_estimated_days}d</div>
              <div className="text-xs text-gray-400">Working Days</div>
            </div>
            <div className="bg-purple-900/40 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-purple-300">{effort.fr_estimated_hours}h</div>
              <div className="text-xs text-gray-400">FR Hours</div>
            </div>
            <div className="bg-orange-900/40 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-orange-300">{effort.nfr_estimated_hours}h</div>
              <div className="text-xs text-gray-400">NFR Hours</div>
            </div>
          </div>
        )}
      </div>

      {/* Graph Narrative */}
      {cb.graph_summary && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <SectionHeader icon="🗺️" title="Planning Narrative" />
          <blockquote className="border-l-4 border-blue-500 pl-4 text-gray-300 text-sm leading-relaxed whitespace-pre-line">
            {cb.graph_summary}
          </blockquote>
        </div>
      )}

      {/* Team Allocation */}
      {team.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <SectionHeader icon="👥" title="Team Allocation" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400 border-b border-gray-700">
                  <th className="pb-3 pr-4">Role</th>
                  <th className="pb-3 pr-4 text-center">Tasks</th>
                  <th className="pb-3 pr-4 text-center">Hours</th>
                  <th className="pb-3">Focus Areas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {team.map((member, i) => (
                  <tr key={i} className="hover:bg-gray-700/50 transition-colors">
                    <td className="py-3 pr-4 font-medium text-white">{member.role}</td>
                    <td className="py-3 pr-4 text-center">
                      <span className="bg-blue-900 text-blue-300 text-xs px-2 py-0.5 rounded-full">
                        {member.task_count}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-center text-gray-300">{member.estimated_hours}h</td>
                    <td className="py-3 text-gray-400 text-xs">{member.focus}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Risk Register */}
      {risks.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
          <SectionHeader icon="⚠️" title="Risk Register" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {risks.map((r, i) => (
              <div key={i} className="bg-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm text-white font-medium">{r.risk}</p>
                  <span className="text-xs bg-red-900 text-red-300 px-2 py-0.5 rounded-full">
                    {r.task_count} task{r.task_count !== 1 ? "s" : ""}
                  </span>
                </div>
                <p className="text-xs text-gray-500">{r.task_ids.slice(0, 5).join(", ")}{r.task_ids.length > 5 ? "…" : ""}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Assumptions & Ambiguity */}
      {(assumptions.length > 0 || ambiguity.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {assumptions.length > 0 && (
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
              <SectionHeader icon="💡" title="Planning Assumptions" />
              <ul className="space-y-2">
                {assumptions.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                    <span className="text-blue-400 mt-0.5 flex-shrink-0">•</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ambiguity.length > 0 && (
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
              <SectionHeader icon="❓" title="Ambiguity Register" />
              <div className="space-y-3">
                {ambiguity.map((item, i) => (
                  <div key={i} className="bg-gray-700 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-yellow-400">{item.task_id}</span>
                      <span className="text-xs text-gray-500">{item.original_source}</span>
                    </div>
                    <p className="text-xs text-gray-300">{item.reason}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Admin Review Status */}
      {brief.admin_review && (
        <div className="bg-gray-800 rounded-xl p-5 border border-gray-700">
          <SectionHeader icon="✅" title="Admin Review Status" />
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
            {["status", "approved", "edited", "rejected", "skipped"].map((k) => (
              <div key={k} className="bg-gray-700 rounded-lg p-3">
                <div className="text-lg font-bold text-white capitalize">
                  {String((brief.admin_review as Record<string, unknown>)?.[k] ?? "—")}
                </div>
                <div className="text-xs text-gray-400 capitalize">{k}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
