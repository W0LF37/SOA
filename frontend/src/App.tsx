import React, { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Calendar, Network,
  Activity, AlertTriangle, MessageSquare, Sparkles,
  ClipboardCheck, FileText, LogOut, Database, BarChart2,
  GraduationCap, UserCog,
} from "lucide-react";
import { getChatMessages } from "./lib/api";

import { useAppStore } from "./lib/store";

const Dashboard = React.lazy(() => import("./pages/Dashboard"));
const PlanPage = React.lazy(() => import("./pages/PlanPage"));
const ChatPage = React.lazy(() => import("./pages/ChatPage"));
const GanttPage = React.lazy(() => import("./pages/GanttPage"));
const GraphPage = React.lazy(() => import("./pages/GraphPage"));
const MonitorPage = React.lazy(() => import("./pages/MonitorPage"));
const RisksPage = React.lazy(() => import("./pages/RisksPage"));
const AdminReviewPage = React.lazy(() => import("./pages/AdminReviewPage"));
const BriefPage = React.lazy(() => import("./pages/BriefPage"));
const KBPage = React.lazy(() => import("./pages/KBPage"));
const EvaluatePage = React.lazy(() => import("./pages/EvaluatePage"));
const StudentWorkspace = React.lazy(() => import("./pages/StudentWorkspace"));
const LoginPage = React.lazy(() => import("./pages/LoginPage"));

const NAV_SUPERVISOR = [
  {
    title: "Overview",
    items: [
      { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
      { to: "/plan", icon: FileText, label: "View Plan" },
    ],
  },
  {
    title: "Analytics",
    items: [
      { to: "/gantt", icon: Calendar, label: "Gantt Chart" },
      { to: "/graph", icon: Network, label: "Task Graph" },
      { to: "/monitor", icon: Activity, label: "Git Monitor" },
      { to: "/risks", icon: AlertTriangle, label: "Risk Indicators" },
    ],
  },
  {
    title: "Review",
    items: [
      { to: "/brief", icon: FileText, label: "Committee Brief" },
      { to: "/admin", icon: ClipboardCheck, label: "Admin Review" },
      { to: "/chat", icon: MessageSquare, label: "Communication" },
    ],
  },
  {
    title: "System",
    items: [
      { to: "/kb", icon: Database, label: "Knowledge Base" },
      { to: "/evaluate", icon: BarChart2, label: "Evaluation" },
    ],
  },
] as const;

function Sidebar() {
  const role = useAppStore((s) => s.role);
  const auth = useAppStore((s) => s.auth);
  const logout = useAppStore((s) => s.logout);
  const navigate = useNavigate();
  const sections = NAV_SUPERVISOR;
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await getChatMessages();
        const fiveMinAgo = Date.now() - 5 * 60 * 1000;
        const newMsgs = data.messages.filter(
          (m) => m.role !== role && new Date(m.created_at).getTime() > fiveMinAgo
        );
        setUnreadCount(newMsgs.length);
      } catch { /* silent */ }
    };
    void check();
    const t = setInterval(check, 10000);
    return () => clearInterval(t);
  }, [role]);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <aside
      className="sidebar"
      style={{ "--role-color": role === "Student" ? "#2563eb" : "#7c3aed" } as React.CSSProperties}
    >
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          <Sparkles size={18} />
        </div>
        <div>
          <div className="sidebar-title">CritiPlan</div>
          <div className="sidebar-sub">AI Project Manager</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {sections.map((section, index) => (
          <React.Fragment key={section.title}>
            <div className="sidebar-section" style={index > 0 ? { marginTop: 12 } : undefined}>
              {section.title}
            </div>
            {section.items.map(({ to, icon: Icon, label }) => {
              const isChat = to === "/chat";
              return (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/dashboard"}
                  className="card-glow"
                  onClick={isChat ? () => setUnreadCount(0) : undefined}
                >
                  <span style={{ position: "relative", display: "flex", alignItems: "center" }}>
                    <Icon size={17} />
                    {isChat && unreadCount > 0 && (
                      <span style={{
                        position: "absolute", top: -6, right: -8,
                        background: "#ef4444", color: "#fff",
                        fontSize: 9, fontWeight: 800, borderRadius: 99,
                        minWidth: 14, height: 14, display: "flex", alignItems: "center",
                        justifyContent: "center", padding: "0 3px", lineHeight: 1,
                      }}>
                        {unreadCount > 9 ? "9+" : unreadCount}
                      </span>
                    )}
                  </span>
                  {label}
                </NavLink>
              );
            })}
          </React.Fragment>
        ))}
      </nav>

      <div className="sidebar-role" style={{ gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {role === "Student"
            ? <GraduationCap size={18} color="#60a5fa" />
            : <UserCog size={18} color="#a78bfa" />}
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#f1f5f9" }}>
              {auth?.name ?? role}
            </div>
            <div style={{ fontSize: 11, color: "#64748b" }}>{role}</div>
          </div>
        </div>
        <button
          onClick={handleLogout}
          title="Sign Out"
          style={{
            marginLeft: "auto",
            background: "transparent",
            border: "1px solid #334155",
            borderRadius: 7,
            padding: "6px 8px",
            cursor: "pointer",
            color: "#64748b",
            display: "flex",
            alignItems: "center",
            gap: 5,
            fontSize: 12,
          }}
        >
          <LogOut size={13} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const auth = useAppStore((s) => s.auth);
  if (!auth?.loggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RouteFallback() {
  return (
    <div
      style={{
        minHeight: "50vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#94a3b8",
        fontSize: 14,
      }}
    >
      Loading workspace...
    </div>
  );
}

function AppShell() {
  const role = useAppStore((s) => s.role);
  const refreshAll = useAppStore((s) => s.refreshAll);
  const refreshBrief = useAppStore((s) => s.refreshBrief);
  const refreshKBStats = useAppStore((s) => s.refreshKBStats);

  useEffect(() => {
    void refreshAll();
    void refreshBrief();
    void refreshKBStats();
  }, [refreshAll, refreshBrief, refreshKBStats]);

  if (role === "Student") {
    return (
      <div style={{ minHeight: "100vh", background: "inherit" }}>
        <React.Suspense fallback={<RouteFallback />}>
          <StudentWorkspace />
        </React.Suspense>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="content">
        <React.Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/"           element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard"  element={<Dashboard />} />
            <Route path="/plan"       element={<PlanPage />} />
            <Route path="/gantt"      element={<GanttPage />} />
            <Route path="/graph"      element={<GraphPage />} />
            <Route path="/monitor"    element={<MonitorPage />} />
            <Route path="/risks"      element={<RisksPage />} />
            <Route path="/chat"       element={<ChatPage />} />
            <Route path="/brief"      element={<BriefPage />} />
            <Route path="/admin"      element={<AdminReviewPage />} />
            <Route path="/kb"         element={<KBPage />} />
            <Route path="/evaluate"   element={<EvaluatePage />} />
          </Routes>
        </React.Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <React.Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        />
      </Routes>
    </React.Suspense>
  );
}
