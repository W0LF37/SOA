import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Lock, User, Hash, GraduationCap, UserCog, Eye, EyeOff } from "lucide-react";
import { useAppStore } from "../lib/store";

const CREDENTIALS = {
  Student: {
    id: "STU-2024",
    name: "Ahmed Khalid",
    password: "student123",
  },
  Supervisor: {
    code: "SUPER-ADM",
    password: "supervisor123",
  },
} as const;

function normalizeText(value: string) {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function normalizeCode(value: string) {
  return value.trim().toUpperCase();
}

export default function LoginPage() {
  const navigate = useNavigate();
  const login = useAppStore((s) => s.login);

  const [tab, setTab] = useState<"Student" | "Supervisor">("Student");
  const [studentId, setStudentId] = useState("");
  const [studentName, setStudentName] = useState("");
  const [supCode, setSupCode] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const isStudent = tab === "Student";
  const roleColor = isStudent ? "#2563eb" : "#7c3aed";

  function handleTabSwitch(newTab: "Student" | "Supervisor") {
    setTab(newTab);
    setError("");
    setPassword("");
    setShowPassword(false);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    setTimeout(() => {
      const normalizedPassword = password.trim();

      if (isStudent) {
        if (
          normalizeCode(studentId) === CREDENTIALS.Student.id &&
          normalizeText(studentName) === normalizeText(CREDENTIALS.Student.name) &&
          normalizedPassword === CREDENTIALS.Student.password
        ) {
          login({ loggedIn: true, role: "Student", name: studentName.trim() });
          navigate("/", { replace: true });
        } else {
          setError("Invalid Student ID, name, or password.");
          setLoading(false);
        }
      } else {
        if (
          normalizeCode(supCode) === CREDENTIALS.Supervisor.code &&
          normalizedPassword === CREDENTIALS.Supervisor.password
        ) {
          login({ loggedIn: true, role: "Supervisor", name: "Dr. Supervisor" });
          navigate("/", { replace: true });
        } else {
          setError("Invalid supervisor code or password.");
          setLoading(false);
        }
      }
    }, 400);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "radial-gradient(ellipse at 50% 0%, #1a1040 0%, #0f172a 60%)",
        padding: "24px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 440,
          background: "rgba(15,23,42,0.97)",
          border: "1px solid #1e293b",
          borderRadius: 20,
          padding: "40px 36px 36px",
          boxShadow: "0 25px 60px rgba(0,0,0,0.5)",
        }}
      >
        {/* Brand */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 14,
              background: `linear-gradient(135deg, ${roleColor}33, ${roleColor}11)`,
              border: `1px solid ${roleColor}44`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
              transition: "all 0.3s",
            }}
          >
            <Sparkles size={24} color={roleColor} />
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: "#f1f5f9", letterSpacing: "-0.02em" }}>
            CritiPlan
          </div>
          <div style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>
            AI Project Manager · Powered by Ollama
          </div>
        </div>

        {/* Tab switcher */}
        <div
          style={{
            display: "flex",
            background: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: 10,
            padding: 4,
            marginBottom: 28,
          }}
        >
          {(["Student", "Supervisor"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => handleTabSwitch(t)}
              style={{
                flex: 1,
                padding: "9px 0",
                borderRadius: 7,
                border: "none",
                cursor: "pointer",
                fontWeight: 600,
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                transition: "all 0.2s",
                background: tab === t
                  ? (t === "Student" ? "#2563eb" : "#7c3aed")
                  : "transparent",
                color: tab === t ? "#fff" : "#64748b",
                borderTop: t === "Student"
                  ? (tab === t ? "2px solid #2563eb" : "2px solid transparent")
                  : (tab === t ? "2px solid #7c3aed" : "2px solid transparent"),
              }}
            >
              {t === "Student" ? <GraduationCap size={18} /> : <UserCog size={18} />}
              {t}
            </button>
          ))}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {isStudent ? (
            <>
              <Field
                label="Student ID"
                icon={<Hash size={15} color="#475569" />}
                value={studentId}
                onChange={setStudentId}
                placeholder="STU-2024"
                autoComplete="username"
              />
              <Field
                label="Full Name"
                icon={<User size={15} color="#475569" />}
                value={studentName}
                onChange={setStudentName}
                placeholder="Ahmed Khalid"
                autoComplete="name"
              />
            </>
          ) : (
            <Field
              label="Supervisor Code"
              icon={<Hash size={15} color="#475569" />}
              value={supCode}
              onChange={setSupCode}
              placeholder="SUPER-ADM"
              autoComplete="username"
            />
          )}

          <Field
            label="Password"
            icon={<Lock size={15} color="#475569" />}
            value={password}
            onChange={setPassword}
            placeholder="••••••••••"
            type="password"
            autoComplete="current-password"
            showPasswordToggle
            showPassword={showPassword}
            onTogglePassword={() => setShowPassword((current) => !current)}
          />

          {error && (
            <div
              style={{
                background: "#450a0a",
                border: "1px solid #7f1d1d",
                borderRadius: 8,
                padding: "10px 14px",
                fontSize: 13,
                color: "#fca5a5",
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: 4,
              padding: "13px 0",
              borderRadius: 10,
              border: "none",
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: 700,
              fontSize: 14,
              background: loading
                ? "#1e293b"
                : `linear-gradient(135deg, ${roleColor}, ${isStudent ? "#1d4ed8" : "#6d28d9"})`,
              color: loading ? "#475569" : "#fff",
              letterSpacing: "0.01em",
              transition: "all 0.2s",
            }}
          >
            {loading
              ? "Signing in..."
              : isStudent
              ? "Sign In as Student →"
              : "Sign In as Supervisor →"}
          </button>
        </form>

        <div style={{ textAlign: "center", marginTop: 24, fontSize: 12, color: "#334155" }}>
          Demo account: {isStudent ? "STU-2024 / Ahmed Khalid" : "SUPER-ADM"} · password hidden
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  icon,
  value,
  onChange,
  placeholder,
  type = "text",
  autoComplete,
  showPasswordToggle,
  showPassword,
  onTogglePassword,
}: {
  label: string;
  icon: React.ReactNode;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  type?: string;
  autoComplete?: string;
  showPasswordToggle?: boolean;
  showPassword?: boolean;
  onTogglePassword?: () => void;
}) {
  const inputType = showPasswordToggle ? (showPassword ? "text" : "password") : type;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", letterSpacing: "0.05em" }}>
        {label.toUpperCase()}
      </label>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: 9,
          padding: "0 14px",
        }}
      >
        {icon}
        <div style={{ flex: 1, position: "relative" }}>
          <input
            type={inputType}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            autoComplete={autoComplete}
            required
            style={{
              width: "100%",
              background: "transparent",
              border: "none",
              outline: "none",
              padding: "11px 0",
              paddingRight: showPasswordToggle ? 40 : 0,
              fontSize: 14,
              color: "#f1f5f9",
              fontFamily: "inherit",
            }}
          />
          {showPasswordToggle && onTogglePassword ? (
            <button
              type="button"
              onClick={onTogglePassword}
              style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#64748b", display: "flex", alignItems: "center" }}
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
