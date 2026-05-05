import { useEffect, useState } from "react";
import {
  getAdminQueue,
  submitReview,
  type AdminQueueItem,
  type ReviewDecision,
  type ReviewResult,
} from "../lib/api";

type DecisionState = {
  action: ReviewDecision["action"];
  new_title: string;
  note?: string;
};

const ACTION_STYLES: Record<ReviewDecision["action"], string> = {
  approved: "bg-green-600 hover:bg-green-700 text-white",
  edited: "bg-yellow-500 hover:bg-yellow-600 text-white",
  rejected: "bg-red-600 hover:bg-red-700 text-white",
  skipped: "bg-gray-500 hover:bg-gray-600 text-white",
};

const COMPLEXITY_BADGE: Record<number, string> = {
  1: "bg-green-900 text-green-300",
  2: "bg-blue-900 text-blue-300",
  3: "bg-yellow-900 text-yellow-300",
  4: "bg-orange-900 text-orange-300",
  5: "bg-red-900 text-red-300",
};

export default function AdminReviewPage() {
  const [items, setItems] = useState<AdminQueueItem[]>([]);
  const [status, setStatus] = useState<string>("loading");
  const [decisions, setDecisions] = useState<Record<string, DecisionState>>({});
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminQueue()
      .then((q) => {
        setItems(q.items);
        setStatus(q.status);
        const initial: Record<string, DecisionState> = {};
        q.items.forEach((item) => {
          initial[item.task_id] = { action: "skipped", new_title: item.title, note: "" };
        });
        setDecisions(initial);
      })
      .catch(() => setStatus("error"));
  }, []);

  const setAction = (taskId: string, action: ReviewDecision["action"]) => {
    setDecisions((prev) => ({ ...prev, [taskId]: { ...prev[taskId], action } }));
  };

  const setTitle = (taskId: string, new_title: string) => {
    setDecisions((prev) => ({ ...prev, [taskId]: { ...prev[taskId], new_title } }));
  };

  const setNote = (taskId: string, note: string) => {
    setDecisions((prev) => ({ ...prev, [taskId]: { ...prev[taskId], note } }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload: ReviewDecision[] = Object.entries(decisions).map(([task_id, d]) => ({
        task_id,
        action: d.action,
        new_title: d.action === "edited" ? d.new_title : undefined,
        note: d.note?.trim() ? d.note.trim() : undefined,
      }));
      const res = await submitReview(payload);
      setResult(res);
    } catch {
      setError("Failed to submit review. Make sure the API is running.");
    } finally {
      setSubmitting(false);
    }
  };

  const decided = Object.values(decisions).filter((d) => d.action !== "skipped").length;
  const total = items.length;

  if (status === "no_pipeline_run" || status === "empty") {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4 text-gray-400">
        <div className="text-5xl">📋</div>
        <p className="text-lg font-medium">No tasks flagged for review</p>
        <p className="text-sm">Run the pipeline first, or all tasks were auto-approved.</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-red-400">
        <p className="text-lg">Could not load review queue. Is the API running?</p>
      </div>
    );
  }

  if (result) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <div className="bg-gray-800 rounded-xl p-8 text-center border border-green-700">
          <div className="text-5xl mb-4">✅</div>
          <h2 className="text-2xl font-bold text-white mb-2">Review Submitted</h2>
          <p className="text-gray-400 mb-6">
            {result.kept_tasks} tasks kept · {result.rejected_tasks} rejected
          </p>
          <div className="grid grid-cols-4 gap-4 text-center">
            {Object.entries(result.counts).map(([action, count]) => (
              <div key={action} className="bg-gray-700 rounded-lg p-3">
                <div className="text-2xl font-bold text-white">{count}</div>
                <div className="text-xs text-gray-400 capitalize">{action}</div>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-500 mt-4">
            Final tasks saved to <code className="text-green-400">data/processed/tasks_final.json</code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-2xl font-bold text-white">Admin Review</h1>
          <p className="text-gray-400 text-sm mt-1">
            {total} task{total !== 1 ? "s" : ""} flagged for manual review
          </p>
          <p className="text-gray-500 text-xs mt-1">
            data/processed/tasks_final.json is created after submitting these decisions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const updated: Record<string, DecisionState> = {};
              items.forEach((item) => {
                if (!decisions[item.task_id] || decisions[item.task_id].action === "skipped") {
                  updated[item.task_id] = {
                    action: "approved",
                    new_title: decisions[item.task_id]?.new_title ?? item.title,
                    note: decisions[item.task_id]?.note ?? "",
                  };
                }
              });
              setDecisions((prev) => ({ ...prev, ...updated }));
            }}
            style={{ background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 8, padding: "8px 14px", color: "#4ade80", fontSize: 12, cursor: "pointer" }}
          >
            ✓ Approve All
          </button>
          {status === "reviewed" && (
            <span className="text-xs bg-blue-900 text-blue-300 px-3 py-1 rounded-full">
              Previously reviewed
            </span>
          )}
        </div>
      </div>

      {/* progress bar */}
      <div className="bg-gray-700 rounded-full h-2 mb-4">
        <div
          className="bg-blue-500 h-2 rounded-full transition-all"
          style={{ width: `${total > 0 ? (decided / total) * 100 : 0}%` }}
        />
      </div>
      <p className="text-xs text-gray-400 mb-4">
        {decided} / {total} decisions made
      </p>

      {/* task cards */}
      <div className="space-y-4">
        {items.map((item) => {
          const d = decisions[item.task_id] || { action: "skipped", new_title: item.title, note: "" };
          return (
            <div
              key={item.task_id}
              className={`bg-gray-800 rounded-xl p-5 border transition-all ${
                d.action === "approved"
                  ? "border-green-700"
                  : d.action === "rejected"
                  ? "border-red-800"
                  : d.action === "edited"
                  ? "border-yellow-700"
                  : "border-gray-700"
              }`}
            >
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-xs font-mono text-gray-500">{item.task_id}</span>
                    <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">
                      {item.req_type}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${COMPLEXITY_BADGE[item.complexity] || "bg-gray-700 text-gray-300"}`}
                    >
                      C{item.complexity}
                    </span>
                    <span className="text-xs bg-gray-700 text-gray-400 px-2 py-0.5 rounded">
                      {item.source}
                    </span>
                    {item.optional && (
                      <span className="text-xs bg-purple-900 text-purple-300 px-2 py-0.5 rounded">
                        optional
                      </span>
                    )}
                  </div>
                  <h3 className="font-semibold text-white text-base">{item.title}</h3>
                  {item.reason && (
                    <p className="text-xs text-yellow-400 mt-1">⚠ {item.reason}</p>
                  )}
                  {item.description && (
                    <p className="text-sm text-gray-400 mt-1 line-clamp-2">{item.description}</p>
                  )}
                </div>

                {/* action buttons */}
                <div className="flex gap-2 flex-shrink-0 flex-wrap">
                  {(["approved", "edited", "rejected", "skipped"] as const).map((action) => (
                    <button
                      key={action}
                      onClick={() => setAction(item.task_id, action)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all border ${
                        d.action === action
                          ? ACTION_STYLES[action] + " ring-2 ring-offset-1 ring-offset-gray-800 ring-current"
                          : "bg-gray-700 text-gray-400 border-gray-600 hover:bg-gray-600"
                      }`}
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>

              {d.action === "edited" && (
                <div className="mt-3">
                  <input
                    type="text"
                    value={d.new_title}
                    onChange={(e) => setTitle(item.task_id, e.target.value)}
                    placeholder="New task title..."
                    className="w-full bg-gray-700 border border-yellow-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                  />
                </div>
              )}

              {(d.action === "edited" || d.action === "rejected") && (
                <textarea
                  placeholder="Add a note for this decision (optional)..."
                  value={d.note ?? ""}
                  onChange={(e) => setNote(item.task_id, e.target.value)}
                  rows={2}
                  style={{ width: "100%", marginTop: 8, background: "#020617", border: "1px solid #334155", borderRadius: 8, color: "#f8fafc", padding: "8px 10px", fontSize: 12, resize: "none" }}
                />
              )}
            </div>
          );
        })}
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="flex justify-end pt-4">
        <button
          onClick={handleSubmit}
          disabled={submitting || total === 0}
          className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl font-semibold text-sm transition-all"
        >
          {submitting ? "Submitting…" : `Submit All Decisions (${total})`}
        </button>
      </div>
    </div>
  );
}
