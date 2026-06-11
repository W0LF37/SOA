import { useEffect, useRef, useState } from "react";
import { Send, CheckCircle, XCircle, Trash2, MessageSquare } from "lucide-react";

import {
  getChatMessages,
  sendChatMessage,
  approvePlan,
  rejectPlan,
  clearChatMessages,
  type ChatMessage,
} from "../lib/api";
import { useAppStore } from "../lib/store";

function statusBadgeStyle(planStatus: string) {
  if (planStatus === "approved") {
    return {
      background: "rgba(34,197,94,0.16)",
      color: "#4ade80",
      border: "1px solid rgba(34,197,94,0.24)",
    };
  }
  if (planStatus === "rejected") {
    return {
      background: "rgba(239,68,68,0.16)",
      color: "#f87171",
      border: "1px solid rgba(239,68,68,0.24)",
    };
  }
  return {
    background: "rgba(2,132,199,0.18)",
    color: "#7dd3fc",
    border: "1px solid rgba(2,132,199,0.30)",
  };
}

export default function ChatPage() {
  const role = useAppStore((s) => s.role);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [message, setMessage] = useState("");
  const [decisionComment, setDecisionComment] = useState("");
  const [planStatus, setPlanStatus] = useState("pending");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function refreshMessages(showLoading = true) {
    if (showLoading) setLoading(true);
    try {
      const data = await getChatMessages();
      setMessages(data.messages);
      setPlanStatus(data.plan_status);
      setError(null);
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : "Unable to load messages.");
    } finally {
      if (showLoading) setLoading(false);
    }
  }

  useEffect(() => {
    void refreshMessages();
    if (planStatus === "approved" || planStatus === "rejected") return;
    const timer = window.setInterval(() => void refreshMessages(false), 5000);
    return () => window.clearInterval(timer);
  }, [planStatus]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const text = message.trim();
    if (!text) {
      setError("Message cannot be empty.");
      return;
    }

    try {
      await sendChatMessage(role, text);
      setMessage("");
      await refreshMessages();
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : "Unable to send message.");
    }
  }

  async function handleApprove() {
    try {
      await approvePlan(decisionComment.trim());
      setDecisionComment("");
      await refreshMessages();
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : "Unable to approve plan.");
    }
  }

  async function handleReject() {
    try {
      await rejectPlan(decisionComment.trim());
      setDecisionComment("");
      await refreshMessages();
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : "Unable to reject plan.");
    }
  }

  async function handleClearHistory() {
    try {
      await clearChatMessages();
      setMessages([]);
      setPlanStatus("pending");
      setDecisionComment("");
      setError(null);
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : "Unable to clear history.");
    }
  }

  const badgeStyle = statusBadgeStyle(planStatus);

  return (
    <section
      style={{
        background: "rgba(15,23,42,0.92)",
        border: "1px solid #1e293b",
        borderRadius: 16,
        display: "flex",
        flexDirection: "column",
        minHeight: 720,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "18px 20px",
          borderBottom: "1px solid #1e293b",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div style={{ fontSize: "1.3rem", fontWeight: 800, color: "#f1f5f9" }}>Communication</div>
            <span
              style={{
                ...badgeStyle,
                display: "inline-flex",
                alignItems: "center",
                padding: "4px 10px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 700,
                textTransform: "capitalize",
              }}
            >
              {planStatus}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "#475569", marginTop: 3 }}>Student ↔ Supervisor messaging channel</div>
        </div>

        {role === "Supervisor" && (
          <button className="danger-btn" style={{ padding: "8px 12px", fontSize: 12 }} onClick={() => void handleClearHistory()}>
            <Trash2 size={14} /> Clear History
          </button>
        )}
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          flex: 1,
          minHeight: 0,
          overflowY: "auto",
          padding: 16,
          gap: 12,
          background: "rgba(2,6,23,0.35)",
        }}
      >
        {!messages.length && !loading ? (
          <div
            style={{
              minHeight: 280,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 10,
              color: "#64748b",
              textAlign: "center",
            }}
          >
            <MessageSquare size={48} style={{ opacity: 0.3 }} />
            <div>No messages yet</div>
          </div>
        ) : null}

        {loading && !messages.length ? (
          <div style={{ color: "#64748b", textAlign: "center", padding: "48px 0" }}>Loading conversation…</div>
        ) : null}

        {messages.map((item) => {
          if (item.type === "approval") {
            return (
              <div key={item.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                <div
                  style={{
                    background: "rgba(34,197,94,0.16)",
                    color: "#4ade80",
                    border: "1px solid rgba(34,197,94,0.24)",
                    padding: "8px 14px",
                    borderRadius: 999,
                    fontSize: 13,
                    fontWeight: 800,
                  }}
                >
                  ✓ Plan Approved
                </div>
                {item.text ? (
                  <div style={{ fontSize: 12, color: "#7dd3fc", textAlign: "center", maxWidth: 460 }}>
                    {item.text}
                  </div>
                ) : null}
              </div>
            );
          }

          if (item.type === "rejection") {
            return (
              <div key={item.id} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                <div
                  style={{
                    background: "rgba(239,68,68,0.16)",
                    color: "#f87171",
                    border: "1px solid rgba(239,68,68,0.24)",
                    padding: "8px 14px",
                    borderRadius: 999,
                    fontSize: 13,
                    fontWeight: 800,
                  }}
                >
                  ✗ Plan Rejected
                </div>
                {item.text ? (
                  <div style={{ fontSize: 12, color: "#7dd3fc", textAlign: "center", maxWidth: 460 }}>
                    {item.text}
                  </div>
                ) : null}
              </div>
            );
          }

          const studentMessage = item.role === "Student";
          return (
            <div
              key={item.id}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: studentMessage ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  background: studentMessage ? "#0369a1" : "#1e293b",
                  border: studentMessage ? "none" : "1px solid #334155",
                  borderRadius: studentMessage ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
                  padding: "10px 16px",
                  maxWidth: "70%",
                  color: "#f1f5f9",
                  lineHeight: 1.55,
                  whiteSpace: "pre-wrap",
                }}
              >
                {item.text}
              </div>
              <div
                title={new Date(item.created_at).toLocaleString()}
                style={{
                  marginTop: 6,
                  fontSize: 11,
                  color: "#64748b",
                  textAlign: studentMessage ? "right" : "left",
                }}
              >
                {item.role} · {new Date(item.created_at).toLocaleTimeString()}
              </div>
            </div>
          );
        })}

        <div ref={bottomRef} />
      </div>

      <div
        style={{
          padding: 16,
          borderTop: "1px solid #1e293b",
          background: "rgba(15,23,42,0.96)",
        }}
      >
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
          <textarea
            rows={2}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
            placeholder="Write a message..."
            style={{
              flex: 1,
              background: "#020617",
              border: "1px solid #334155",
              borderRadius: 12,
              color: "#f8fafc",
              padding: "10px 12px",
              fontSize: 13,
              resize: "none",
            }}
          />
          <button className="primary-btn" onClick={() => void handleSend()}>
            <Send size={15} />
          </button>
        </div>

        {role === "Supervisor" ? (
          <div style={{ marginTop: 16 }}>
            <div
              style={{
                fontSize: 11,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "#64748b",
                fontWeight: 700,
                marginBottom: 8,
              }}
            >
              Supervisor Decision
            </div>
            <textarea
              rows={2}
              value={decisionComment}
              onChange={(event) => setDecisionComment(event.target.value)}
              placeholder="Add a comment (optional)..."
              style={{
                width: "100%",
                background: "#020617",
                border: "1px solid #334155",
                borderRadius: 12,
                color: "#f8fafc",
                padding: "10px 12px",
                fontSize: 13,
                resize: "vertical",
              }}
            />
            <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
              <button className="primary-btn" onClick={() => void handleApprove()}>
                <CheckCircle size={15} /> Approve
              </button>
              <button className="danger-btn" onClick={() => void handleReject()}>
                <XCircle size={15} /> Reject
              </button>
            </div>
          </div>
        ) : null}

        {error ? (
          <div style={{ marginTop: 12, color: "#f87171", fontSize: 13 }}>{error}</div>
        ) : null}
      </div>
    </section>
  );
}
