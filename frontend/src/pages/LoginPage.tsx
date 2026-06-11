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
  const resetWorkspace = useAppStore((s) => s.resetWorkspace);

  const [tab, setTab] = useState<"Student" | "Supervisor">("Student");
  const [studentId, setStudentId] = useState("");
  const [studentName, setStudentName] = useState("");
  const [supCode, setSupCode] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const isStudent = tab === "Student";
  const roleColor = isStudent ? "#0284c7" : "#1e40af";

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
          resetWorkspace();
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
          resetWorkspace();
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
      className="login-aurora-bg"
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        className="login-card fade-up"
        style={{
          width: "100%",
          maxWidth: 440,
          borderRadius: 22,
          padding: "44px 38px 38px",
          position: "relative",
          zIndex: 2,
          ["--role-color" as string]: roleColor,
        } as React.CSSProperties}
      >
        {/* Brand */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div
            className="login-logo float-anim"
            style={{
              width: 58,
              height: 58,
              borderRadius: 16,
              background: `linear-gradient(135deg, ${roleColor}, ${isStudent ? "#0369a1" : "#1e3a8a"})`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 18px",
              transition: "all 0.3s",
            }}
          >
            <Sparkles size={26} color="#ffffff" />
          </div>
          <div className="gradient-text" style={{ fontSize: 26, fontWeight: 900, letterSpacing: "-0.02em" }}>
            AI Project Manager
          </div>
          <div style={{ fontSize: 13, color: "#94a3b8", marginTop: 6, letterSpacing: "0.02em" }}>
            Local Multi-Agent Planning · Powered by Ollama
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
                  ? (t === "Student" ? "#0284c7" : "#1e40af")
                  : "transparent",
                color: tab === t ? "#fff" : "#64748b",
                borderTop: t === "Student"
                  ? (tab === t ? "2px solid #0284c7" : "2px solid transparent")
                  : (tab === t ? "2px solid #1e40af" : "2px solid transparent"),
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
            className={loading ? undefined : "login-cta"}
            style={{
              marginTop: 6,
              padding: "14px 0",
              borderRadius: 11,
              border: "none",
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: 800,
              fontSize: 14,
              background: loading
                ? "#1e293b"
                : `linear-gradient(135deg, ${roleColor}, ${isStudent ? "#0369a1" : "#1e3a8a"})`,
              color: loading ? "#475569" : "#fff",
              letterSpacing: "0.02em",
              transition: "all 0.25s cubic-bezier(.2,.7,.3,1)",
              position: "relative",
              overflow: "hidden",
            }}
          >
            {loading
              ? "Signing in..."
              : isStudent
              ? "Sign In as Student →"
              : "Sign In as Supervisor →"}
          </button>
        </form>

        <div style={{ textAlign: "center", marginTop: 24, fontSize: 12, color: "#475569" }}>
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
