import { useEffect, useState } from "react";
import { AlertCircle, Sparkles, X } from "lucide-react";

import { explainItem, type ExplainRequest, type ExplainResponse } from "../lib/api";

type ExplainPopupProps = {
  isOpen: boolean;
  onClose: () => void;
  contextType: "task" | "risk" | "critic";
  itemId: string;
  itemTitle: string;
  question?: string;
};

export default function ExplainPopup({
  isOpen,
  onClose,
  contextType,
  itemId,
  itemTitle,
  question,
}: ExplainPopupProps) {
  const [response, setResponse] = useState<ExplainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setResponse(null);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;

    async function loadExplanation() {
      setLoading(true);
      setError(null);
      setResponse(null);

      const request: ExplainRequest = {
        context_type: contextType,
        item_id: itemId,
        question,
      };

      try {
        const result = await explainItem(request);
        if (!cancelled) setResponse(result);
      } catch (err) {
        if (cancelled) return;
        const status = (err as { response?: { status?: number; data?: { detail?: string } } }).response?.status;
        const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
        setError(status === 503 ? "Ollama not running" : detail || "Unable to load AI explanation.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadExplanation();

    return () => {
      cancelled = true;
    };
  }, [contextType, isOpen, itemId, question]);

  if (!isOpen) return null;

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.72)",
          zIndex: 9999,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 20,
        }}
      >
        <div
          onClick={(event) => event.stopPropagation()}
          role="dialog"
          aria-modal="true"
          style={{
            width: "100%",
            maxWidth: 560,
            background: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: 18,
            boxShadow: "0 24px 70px rgba(2,6,23,0.55)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "16px 18px",
              borderBottom: "1px solid #1e293b",
            }}
          >
            <Sparkles size={18} color="#60a5fa" />
            <div style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc" }}>AI Explanation</div>
            <button
              onClick={onClose}
              aria-label="Close"
              style={{
                marginLeft: "auto",
                width: 32,
                height: 32,
                borderRadius: 8,
                border: "1px solid #334155",
                background: "#0a1120",
                color: "#94a3b8",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
              }}
            >
              <X size={16} />
            </button>
          </div>

          <div style={{ padding: 18 }}>
            <div
              style={{
                background: "#0a1120",
                border: "1px solid #1e293b",
                borderRadius: 14,
                padding: 14,
                marginBottom: 16,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span
                  style={{
                    fontFamily: "monospace",
                    background: "rgba(37,99,235,0.14)",
                    color: "#93c5fd",
                    border: "1px solid rgba(37,99,235,0.24)",
                    padding: "4px 8px",
                    borderRadius: 8,
                    fontWeight: 800,
                    fontSize: 12,
                  }}
                >
                  {itemId}
                </span>
                <span style={{ color: "#f1f5f9", fontWeight: 700, fontSize: 14 }}>{itemTitle}</span>
              </div>
            </div>

            <div style={{ minHeight: 180 }}>
              {loading ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 14,
                    padding: "28px 10px",
                    color: "#94a3b8",
                  }}
                >
                  <div
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: "50%",
                      border: "3px solid #1e293b",
                      borderTopColor: "#60a5fa",
                      animation: "explain-popup-spin 0.9s linear infinite",
                    }}
                  />
                  <div style={{ fontSize: 14, fontWeight: 600 }}>AI is thinking...</div>
                </div>
              ) : null}

              {!loading && error ? (
                <div
                  style={{
                    display: "flex",
                    gap: 10,
                    alignItems: "flex-start",
                    background: "rgba(127,29,29,0.2)",
                    border: "1px solid rgba(248,113,113,0.28)",
                    borderRadius: 12,
                    padding: 14,
                    color: "#fca5a5",
                  }}
                >
                  <AlertCircle size={18} color="#f87171" style={{ flexShrink: 0, marginTop: 1 }} />
                  <div style={{ fontSize: 14, lineHeight: 1.6 }}>{error}</div>
                </div>
              ) : null}

              {!loading && !error && response ? (
                <div
                  style={{
                    color: "#cbd5e1",
                    lineHeight: 1.8,
                    whiteSpace: "pre-wrap",
                    fontSize: 14,
                  }}
                >
                  {response.explanation}
                </div>
              ) : null}
            </div>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              padding: "0 18px 18px",
            }}
          >
            <button
              onClick={onClose}
              style={{
                background: "#1e293b",
                border: "1px solid #334155",
                borderRadius: 10,
                padding: "9px 16px",
                color: "#cbd5e1",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              Close
            </button>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes explain-popup-spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </>
  );
}
