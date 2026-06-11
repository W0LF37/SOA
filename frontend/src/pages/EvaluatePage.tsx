import { useEffect, useState } from "react";
import { getEvaluationResults, runEvaluation, type AblationReport, type EvalSample, type EvaluationReport } from "../lib/api";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function ScoreRing({ score, label }: { score: number; label: string }) {
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? "#22c55e" : pct >= 60 ? "#eab308" : "#ef4444";
  const r = 28;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={r} fill="none" stroke="#374151" strokeWidth="8" />
        <circle
          cx="40" cy="40" r={r} fill="none"
          stroke={color} strokeWidth="8"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 40 40)"
        />
        <text x="40" y="44" textAnchor="middle" fill="white" fontSize="14" fontWeight="bold">
          {pct}%
        </text>
      </svg>
      <p className="text-xs text-gray-400 text-center">{label}</p>
    </div>
  );
}

function metricCellTone(value: number, invert = false) {
  const normalized = invert ? 1 - value : value;
  if (normalized > 0.8) return { bg: "rgba(34,197,94,0.14)", color: "#4ade80" };
  if (normalized > 0.6) return { bg: "rgba(234,179,8,0.14)", color: "#facc15" };
  return { bg: "rgba(239,68,68,0.14)", color: "#f87171" };
}

function average(values: number[]) {
  const filtered = values.filter((value) => Number.isFinite(value));
  return filtered.length ? filtered.reduce((sum, value) => sum + value, 0) / filtered.length : 0;
}

function SampleRow({ s }: { s: EvalSample }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr
        className="border-b border-gray-700 hover:bg-gray-700/50 cursor-pointer transition-colors"
        onClick={() => setOpen(!open)}
      >
        <td className="py-3 px-4 text-sm text-white">{s.sample_id}</td>
        <td className="py-3 px-4">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            s.passed ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"
          }`}>
            {s.passed ? "PASS" : "FAIL"}
          </span>
        </td>
        <td className="py-3 px-4 text-sm text-gray-300 text-center">{s.task_count}</td>
        <td className="py-3 px-4 text-sm text-gray-300 text-center">{s.fr_count}</td>
        <td className="py-3 px-4 text-sm text-gray-300 text-center">{s.nfr_count}</td>
        <td className="py-3 px-4 text-sm text-center">
          <span className={`font-medium ${
            s.req_coverage >= 0.8 ? "text-green-400" : s.req_coverage >= 0.6 ? "text-yellow-400" : "text-red-400"
          }`}>
            {Math.round(s.req_coverage * 100)}%
          </span>
        </td>
        <td className="py-3 px-4 text-sm text-center">
          <span className={`font-medium ${
            s.overall_score >= 0.8 ? "text-green-400" : s.overall_score >= 0.6 ? "text-yellow-400" : "text-red-400"
          }`}>
            {s.overall_score.toFixed(3)}
          </span>
        </td>
        <td className="py-3 px-4 text-gray-500 text-xs text-center">{open ? "▲" : "▼"}</td>
      </tr>
      {open && (
        <tr className="bg-gray-800/80 border-b border-gray-700">
          <td colSpan={8} className="px-4 py-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              {[
                { label: "Coverage Score", v: s.coverage_score },
                { label: "Classification", v: s.classification_score },
                { label: "Complexity", v: s.complexity_score },
                { label: "Dependency", v: s.dependency_score },
              ].map(({ label, v }) => (
                <div key={label} className="bg-gray-700 rounded p-2 text-center">
                  <div className={`font-bold text-sm ${v >= 0.8 ? "text-green-400" : v >= 0.6 ? "text-yellow-400" : "text-red-400"}`}>
                    {(v * 100).toFixed(1)}%
                  </div>
                  <div className="text-gray-400">{label}</div>
                </div>
              ))}
              {s.mmre >= 0 && (
                <div className="bg-gray-700 rounded p-2 text-center">
                  <div className="font-bold text-sm text-blue-300">{s.mmre.toFixed(3)}</div>
                  <div className="text-gray-400">MMRE</div>
                </div>
              )}
              {s.pred25 >= 0 && (
                <div className="bg-gray-700 rounded p-2 text-center">
                  <div className="font-bold text-sm text-blue-300">{(s.pred25 * 100).toFixed(1)}%</div>
                  <div className="text-gray-400">PRED(25)</div>
                </div>
              )}
              {s.f1_fr >= 0 && (
                <div className="bg-gray-700 rounded p-2 text-center">
                  <div className="font-bold text-sm text-purple-300">{s.f1_fr.toFixed(3)}</div>
                  <div className="text-gray-400">F1-FR</div>
                </div>
              )}
              {s.f1_nfr >= 0 && (
                <div className="bg-gray-700 rounded p-2 text-center">
                  <div className="font-bold text-sm text-purple-300">{s.f1_nfr.toFixed(3)}</div>
                  <div className="text-gray-400">F1-NFR</div>
                </div>
              )}
            </div>
            {s.description && (
              <p className="text-xs text-gray-500 mt-2">{s.description}</p>
            )}
            {s.error && (
              <p className="text-xs text-red-400 mt-2">Error: {s.error}</p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export default function EvaluatePage() {
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [ablation, setAblation] = useState<AblationReport | null>(null);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runMsg, setRunMsg] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    getEvaluationResults()
      .then((d) => { setReport(d.report); setRunning(d.running); setAblation(d.ablation); })
      .catch(() => setError("No evaluation report found."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleRun = async () => {
    setRunMsg(null);
    try {
      const res = await runEvaluation();
      setRunMsg(res.message);
      setRunning(true);
      // poll after 30s
      setTimeout(load, 30_000);
    } catch {
      setRunMsg("Failed to start evaluation. Is the API running?");
    }
  };

  const samples = report?.samples ?? [];
  const classificationSamples = samples.filter((sample) => sample.f1_fr >= 0 || sample.f1_nfr >= 0);
  const classificationChartData = classificationSamples.map((sample) => ({
    sample: sample.sample_id,
    f1Fr: sample.f1_fr >= 0 ? sample.f1_fr : 0,
    f1Nfr: sample.f1_nfr >= 0 ? sample.f1_nfr : 0,
  }));
  const avgF1 = average(
    classificationSamples.flatMap((sample) => [sample.f1_fr, sample.f1_nfr].filter((value) => value >= 0)),
  );
  const avgMetrics = classificationSamples.length
    ? {
        f1Fr: average(classificationSamples.map((sample) => sample.f1_fr).filter((value) => value >= 0)),
        f1Nfr: average(classificationSamples.map((sample) => sample.f1_nfr).filter((value) => value >= 0)),
        mmre: average(classificationSamples.map((sample) => sample.mmre).filter((value) => value >= 0)),
        pred25: average(classificationSamples.map((sample) => sample.pred25).filter((value) => value >= 0)),
        coverage: average(classificationSamples.map((sample) => sample.req_coverage).filter((value) => value >= 0)),
      }
    : null;
  const llmSamples = samples.filter((sample) => sample.used_fallback === false);
  const fallbackSamples = samples.filter((sample) => sample.used_fallback === true);
  const llmAvgScore = llmSamples.length ? average(llmSamples.map((sample) => sample.overall_score)) : null;
  const fallbackAvgScore = fallbackSamples.length ? average(fallbackSamples.map((sample) => sample.overall_score)) : null;
  const aiDelta = llmAvgScore != null && fallbackAvgScore != null
    ? ((llmAvgScore - fallbackAvgScore) * 100)
    : null;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <div className="animate-spin text-3xl mr-3">⚙</div>
        <span>Loading evaluation report…</span>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Evaluation Metrics</h1>
          <p className="text-sm text-gray-400 mt-1">
            Ground truth evaluation of the planning pipeline
          </p>
        </div>
        <button
          onClick={handleRun}
          disabled={running}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-all"
        >
          {running ? "⚙ Running…" : "Run New Evaluation"}
        </button>
      </div>

      {runMsg && (
        <div className="bg-blue-900/40 border border-blue-700 rounded-xl p-3 text-sm text-blue-300">
          {runMsg}
        </div>
      )}

      {error && !report && (
        <div className="flex flex-col items-center justify-center h-48 gap-3 text-gray-400">
          <div className="text-5xl">📊</div>
          <p>{error}</p>
          <button onClick={handleRun} className="text-sm text-blue-400 hover:underline">
            Run evaluation now
          </button>
        </div>
      )}

      {report && (
        <>
          {/* Score rings */}
          <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
            <h2 className="text-base font-bold text-white mb-5">System Scores</h2>
            <div className="flex flex-wrap justify-around gap-6">
              <ScoreRing score={report.overall_score ?? 0} label="Overall Score" />
              <ScoreRing score={report.pass_rate ?? 0} label="Pass Rate" />
              {report.samples?.[0]?.coverage_score != null && (
                <ScoreRing
                  score={report.samples.reduce((a, s) => a + s.coverage_score, 0) / report.samples.length}
                  label="Avg Coverage"
                />
              )}
              {report.samples?.[0]?.complexity_score != null && (
                <ScoreRing
                  score={report.samples.reduce((a, s) => a + s.complexity_score, 0) / report.samples.length}
                  label="Complexity Balance"
                />
              )}
              {report.samples?.[0]?.dependency_score != null && (
                <ScoreRing
                  score={report.samples.reduce((a, s) => a + s.dependency_score, 0) / report.samples.length}
                  label="Dependency Score"
                />
              )}
            </div>
            <div className="grid grid-cols-3 gap-4 mt-6 text-center">
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-xl font-bold text-white">{report.sample_count}</div>
                <div className="text-xs text-gray-400">Test Samples</div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-xl font-bold text-green-400">
                  {report.samples?.filter((s) => s.passed).length ?? 0}
                </div>
                <div className="text-xs text-gray-400">Passed</div>
              </div>
              <div className="bg-gray-700 rounded-lg p-3">
                <div className="text-xl font-bold text-red-400">
                  {report.samples?.filter((s) => !s.passed).length ?? 0}
                </div>
                <div className="text-xs text-gray-400">Failed</div>
              </div>
            </div>
          </div>

          {classificationSamples.length > 0 && (
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 space-y-5">
              <div>
                <h2 className="text-base font-bold text-white">Classification Performance</h2>
                <p className="text-xs text-gray-400 mt-1">Per-sample F1 scores for FR/NFR classification plus effort estimation metrics.</p>
              </div>

              <div style={{ width: "100%", height: 300 }}>
                <ResponsiveContainer>
                  <BarChart data={classificationChartData} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="sample" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                    <YAxis stroke="#94a3b8" domain={[0, 1]} tickFormatter={(value) => `${Math.round(value * 100)}%`} tick={{ fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ background: "#111827", border: "1px solid #374151", borderRadius: 10, color: "#f9fafb" }}
                      formatter={(value) => `${(Number(value ?? 0) * 100).toFixed(1)}%`}
                    />
                    <ReferenceLine
                      y={avgF1}
                      stroke="#fbbf24"
                      strokeDasharray="4 4"
                      label={{ value: `Avg F1 ${(avgF1 * 100).toFixed(1)}%`, fill: "#fbbf24", position: "insideTopRight" }}
                    />
                    <Bar dataKey="f1Fr" name="F1-FR" radius={[6, 6, 0, 0]}>
                      {classificationChartData.map((_, index) => (
                        <Cell key={`fr-${index}`} fill="#3b82f6" />
                      ))}
                    </Bar>
                    <Bar dataKey="f1Nfr" name="F1-NFR" radius={[6, 6, 0, 0]}>
                      {classificationChartData.map((_, index) => (
                        <Cell key={`nfr-${index}`} fill="#7c3aed" />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-700/50 text-gray-300">
                    <tr>
                      <th className="py-3 px-4 text-left">Sample</th>
                      <th className="py-3 px-4 text-center">F1-FR</th>
                      <th className="py-3 px-4 text-center">F1-NFR</th>
                      <th className="py-3 px-4 text-center">MMRE</th>
                      <th className="py-3 px-4 text-center">PRED(25)</th>
                      <th className="py-3 px-4 text-center">Coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classificationSamples.map((sample) => {
                      const f1FrTone = metricCellTone(sample.f1_fr);
                      const f1NfrTone = metricCellTone(sample.f1_nfr);
                      const mmreTone = metricCellTone(sample.mmre, true);
                      const predTone = metricCellTone(sample.pred25);
                      const coverageTone = metricCellTone(sample.req_coverage);
                      return (
                        <tr key={`metrics-${sample.sample_id}`} className="border-b border-gray-700">
                          <td className="py-3 px-4 text-white">{sample.sample_id}</td>
                          <td className="py-3 px-4 text-center" style={{ color: f1FrTone.color, background: f1FrTone.bg }}>{sample.f1_fr.toFixed(3)}</td>
                          <td className="py-3 px-4 text-center" style={{ color: f1NfrTone.color, background: f1NfrTone.bg }}>{sample.f1_nfr.toFixed(3)}</td>
                          <td className="py-3 px-4 text-center" style={{ color: mmreTone.color, background: mmreTone.bg }}>{sample.mmre.toFixed(3)}</td>
                          <td className="py-3 px-4 text-center" style={{ color: predTone.color, background: predTone.bg }}>{(sample.pred25 * 100).toFixed(1)}%</td>
                          <td className="py-3 px-4 text-center" style={{ color: coverageTone.color, background: coverageTone.bg }}>{(sample.req_coverage * 100).toFixed(1)}%</td>
                        </tr>
                      );
                    })}
                    {avgMetrics && (
                      <tr className="font-bold bg-gray-700/40">
                        <td className="py-3 px-4 text-white">Average</td>
                        <td className="py-3 px-4 text-center text-blue-300">{avgMetrics.f1Fr.toFixed(3)}</td>
                        <td className="py-3 px-4 text-center text-purple-300">{avgMetrics.f1Nfr.toFixed(3)}</td>
                        <td className="py-3 px-4 text-center text-blue-200">{avgMetrics.mmre.toFixed(3)}</td>
                        <td className="py-3 px-4 text-center text-green-300">{(avgMetrics.pred25 * 100).toFixed(1)}%</td>
                        <td className="py-3 px-4 text-center text-green-300">{(avgMetrics.coverage * 100).toFixed(1)}%</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {llmAvgScore != null && fallbackAvgScore != null && (
                <div className="bg-gray-700/40 border border-gray-600 rounded-xl p-4">
                  <div className="text-sm font-bold text-white mb-3">AI Planning vs Direct Planning</div>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-400 mb-1">LLM Samples Avg</div>
                      <div className="text-lg font-bold text-blue-300">{(llmAvgScore * 100).toFixed(1)}%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-400 mb-1">Direct Planning Avg</div>
                      <div className="text-lg font-bold text-yellow-300">{(fallbackAvgScore * 100).toFixed(1)}%</div>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3">
                      <div className="text-xs text-gray-400 mb-1">Delta</div>
                      <div className={`text-lg font-bold ${aiDelta != null && aiDelta >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {aiDelta != null ? `${aiDelta >= 0 ? "+" : ""}${aiDelta.toFixed(1)}% improvement with AI` : "n/a"}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {ablation?.conditions && (
            <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 space-y-4">
              <div>
                <h2 className="text-base font-bold text-white">Ablation Study - Layer Contribution</h2>
                <p className="text-xs text-gray-400 mt-1">
                  Each condition adds one architectural layer. Z = raw LLM baseline, R = rules only, K = rules + RAG KB, L = full system (LLM + KB).
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-700/50 text-gray-300 text-xs uppercase tracking-wider">
                    <tr>
                      <th className="py-3 px-4 text-left">Condition</th>
                      <th className="py-3 px-4 text-center">Coverage</th>
                      <th className="py-3 px-4 text-center">F1-FR</th>
                      <th className="py-3 px-4 text-center">F1-NFR</th>
                      <th className="py-3 px-4 text-center">MMRE (low)</th>
                      <th className="py-3 px-4 text-center">PRED(25) (high)</th>
                      <th className="py-3 px-4 text-center">Pass%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(["Z", "R", "K", "L"] as const).map((key) => {
                      const c = ablation.conditions?.[key];
                      if (!c) return null;
                      const isOurs = key === "L" || (key === "K" && !ablation.conditions?.["L"]);
                      return (
                        <tr key={key} className={`border-b border-gray-700 ${isOurs ? "bg-blue-900/20" : ""}`}>
                          <td className="py-3 px-4 text-white font-medium">
                            {c.condition}
                            {isOurs && <span className="ml-2 text-xs bg-blue-600 text-white px-1.5 py-0.5 rounded">Ours</span>}
                          </td>
                          {[
                            c.average_coverage_score,
                            c.avg_f1_fr,
                            c.avg_f1_nfr,
                          ].map((v, i) => {
                            const t = metricCellTone(v ?? 0);
                            return (
                              <td key={i} className="py-3 px-4 text-center text-sm" style={{ color: t.color, background: t.bg }}>
                                {v != null && v >= 0 ? `${(v * 100).toFixed(1)}%` : "N/A"}
                              </td>
                            );
                          })}
                          {[c.average_mmre].map((v, i) => {
                            const t = metricCellTone(v != null ? 1 - v : 0);
                            return (
                              <td key={i} className="py-3 px-4 text-center text-sm" style={{ color: t.color, background: t.bg }}>
                                {v != null && v >= 0 ? v.toFixed(3) : "N/A"}
                              </td>
                            );
                          })}
                          {[c.average_pred25].map((v, i) => {
                            const t = metricCellTone(v ?? 0);
                            return (
                              <td key={i} className="py-3 px-4 text-center text-sm" style={{ color: t.color, background: t.bg }}>
                                {v != null && v >= 0 ? `${(v * 100).toFixed(1)}%` : "N/A"}
                              </td>
                            );
                          })}
                          <td className="py-3 px-4 text-center text-sm text-gray-300">
                            {c.pass_rate != null ? `${c.pass_rate}%` : "N/A"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {ablation.llm_available === false && (
                <p className="text-xs text-yellow-400">Warning: Ollama was not available - conditions L and Z were skipped. Start Ollama and re-run ablation to see full comparison.</p>
              )}
            </div>
          )}

          {/* Samples table */}
          {report.samples?.length > 0 && (
            <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-700">
                <h2 className="text-base font-bold text-white">Per-Sample Results</h2>
                <p className="text-xs text-gray-400 mt-0.5">Click a row to expand metrics</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-700/50">
                    <tr className="text-left text-gray-400">
                      <th className="py-3 px-4">Sample</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-center">Tasks</th>
                      <th className="py-3 px-4 text-center">FR</th>
                      <th className="py-3 px-4 text-center">NFR</th>
                      <th className="py-3 px-4 text-center">Coverage</th>
                      <th className="py-3 px-4 text-center">Score</th>
                      <th className="py-3 px-4 text-center"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.samples.map((s) => (
                      <SampleRow key={s.sample_id} s={s} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {report.generated_at && (
            <p className="text-xs text-gray-600 text-right">
              Last evaluated: {new Date(report.generated_at).toLocaleString()}
            </p>
          )}
        </>
      )}
    </div>
  );
}
