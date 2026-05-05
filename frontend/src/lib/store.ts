import { create } from "zustand";

import {
  getAllData,
  getBrief,
  getEvaluationResults,
  getKBStats,
  type AllData,
  type BriefData,
  type EvaluationReport,
  type KBStats,
} from "./api";

export type AuthSession = {
  loggedIn: boolean;
  role: "Student" | "Supervisor";
  name: string;
};

const SESSION_KEY = "critiplan_session";

function loadSession(): AuthSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed.loggedIn || !parsed.role || !parsed.name) return null;
    return parsed;
  } catch {
    return null;
  }
}

type AppState = {
  data: AllData | null;
  brief: BriefData | null;
  evaluation: { report: EvaluationReport | null; ablation: unknown; running: boolean } | null;
  kbStats: KBStats | null;
  role: "Student" | "Supervisor";
  auth: AuthSession | null;
  login: (session: AuthSession) => void;
  logout: () => void;
  loading: boolean;
  error: string | null;
  refreshAll: () => Promise<void>;
  refreshBrief: () => Promise<void>;
  refreshEvaluation: () => Promise<void>;
  refreshKBStats: () => Promise<void>;
};

function toErrorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "Unable to load project data.";
}

const initialSession = loadSession();

export const useAppStore = create<AppState>((set) => ({
  data: null,
  brief: null,
  evaluation: null,
  kbStats: null,
  role: initialSession?.role ?? "Supervisor",
  auth: initialSession,
  loading: false,
  error: null,

  login: (session) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    set({ auth: session, role: session.role });
  },

  logout: () => {
    localStorage.removeItem(SESSION_KEY);
    set({ auth: null, role: "Supervisor" });
  },

  refreshAll: async () => {
    set({ loading: true, error: null });
    try {
      const data = await getAllData();
      set({ data, loading: false });
    } catch (error) {
      set({ error: toErrorMessage(error), loading: false });
    }
  },

  refreshBrief: async () => {
    try {
      const brief = await getBrief();
      set({ brief });
    } catch {
      // brief not available yet — pipeline hasn't run
    }
  },

  refreshEvaluation: async () => {
    try {
      const evaluation = await getEvaluationResults();
      set({ evaluation });
    } catch {
      // evaluation report not available
    }
  },

  refreshKBStats: async () => {
    try {
      const kbStats = await getKBStats();
      set({ kbStats });
    } catch {
      // KB not initialized
    }
  },
}));
