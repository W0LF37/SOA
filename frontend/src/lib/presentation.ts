import type { SprintSummary, Task } from "./api";

export type PresentationSprint = SprintSummary & {
  displayName: string;
  displayGoal: string;
};

export type ExecutionRoadmapPhase = {
  key: string;
  title: string;
  goal: string;
  tasks: Task[];
  totalHours: number;
  durationWeeks: number;
};

const COMMITTEE_SPRINT_PRIORITY: Record<string, number> = {
  "Patient Intake & Scheduling": 1,
  "Clinical Service Delivery": 2,
  "Patient Experience Delivery": 3,
  "External Service Integrations": 4,
  "Patient Communications": 5,
  "Financial Operations": 6,
  "Supervisor Reporting": 7,
  "Security & Compliance Controls": 8,
  "Performance & Continuity Hardening": 9,
  "Identity & Privileged Access": 10,
  "Identity & Access Control": 11,
  "Delivery Sprint": 99,
};

const DISPLAY_GOALS: Record<string, string> = {
  "Patient Intake & Scheduling": "Patient intake, scheduling, and access foundations are ready before downstream care workflows proceed.",
  "Clinical Service Delivery": "Consultation, diagnostics, and treatment workflows are implemented and usable end-to-end.",
  "Patient Experience Delivery": "Patient-facing portal, localization, and self-service journeys are ready for release.",
  "External Service Integrations": "Video, calendar, payment, and partner integrations are connected and ready for workflow use.",
  "Patient Communications": "Notifications and follow-up touchpoints are connected for patient engagement.",
  "Financial Operations": "Billing, claims, and payment workflows are ready for controlled release.",
  "Supervisor Reporting": "Supervisor visibility and KPI reporting are ready for committee review.",
  "Security & Compliance Controls": "Security controls, auditability, and privileged-access safeguards are enforced before go-live.",
  "Performance & Continuity Hardening": "Performance, uptime, and outage continuity safeguards are hardened for launch readiness.",
  "Identity & Privileged Access": "Identity, privileged access, and MFA safeguards are established before protected workflows proceed.",
  "Identity & Access Control": "Identity, access control, and release gates are ready before protected workflows proceed.",
};

const TITLE_OVERRIDES: Array<[RegExp, string]> = [
  [/^Implement national ID registration workflow$/i, "Build patient registration and national ID intake"],
  [/^Implement appointment booking workflow$/i, "Build appointment booking workflow"],
  [/^Implement appointment management workflow$/i, "Build appointment management workflow"],
  [/^Implement patient history and record diagnosis viewing workflow$/i, "Build the patient history and diagnosis workspace"],
  [/^Implement itemized invoices for consultations and lab creation workflow$/i, "Build billing and lab invoicing workflow"],
  [/^Implement appointment reminders to patients notification workflow$/i, "Build appointment reminder notifications"],
  [/^Implement run telemedicine consultations with structured notes, diagnosis reporting workflow$/i, "Deliver telemedicine consultations and structured clinical notes"],
  [/^Implement lab and radiology orders, track result creation workflow$/i, "Build lab and radiology order tracking"],
  [/^Implement invoices, manage insurance claims, record partial creation workflow$/i, "Build billing, insurance claims, and partial-payment workflow"],
  [/^Implement give supervisors KPI reporting workflow$/i, "Deliver supervisor KPI reporting dashboard"],
  [/^Implement SMS and email notification workflow$/i, "Build SMS and email notifications"],
  [/^Implement multilingual localization support$/i, "Launch bilingual patient portal and self-service journeys"],
  [/^Implement video consultation provider workflow$/i, "Integrate the video consultation provider"],
  [/^Implement multi-factor authentication workflow$/i, "Build multi-factor authentication"],
  [/^Implement Graceful continuity for reception workflows during workflow$/i, "Build continuity support for reception operations"],
  [/^Enforce secure payment gateway security controls$/i, "Establish secure payment gateway controls"],
  [/^Enforce sensitive data encryption controls$/i, "Establish sensitive-data encryption controls"],
  [/^Enforce audit logs for privileged actions compliance requirements$/i, "Establish privileged-action audit logging"],
  [/^Enable Arabic\/English RTL\/LTR localization support$/i, "Finalize Arabic/English RTL-LTR interface support"],
  [/^Optimize p95 response-time SLO$/i, "Harden the p95 response-time SLO"],
  [/^Optimize system uptime and reliability constraints$/i, "Harden uptime and reliability controls"],
];

const THEME_RULES: Array<{
  key: string;
  label: string;
  goal: string;
  patterns: RegExp[];
}> = [
  {
    key: "identity",
    label: "Identity & Access Control",
    goal: "Identity, access control, and release gates are ready before protected workflows proceed.",
    patterns: [/identity/i, /national id/i, /authentication/i, /access/i, /\bmfa\b/i, /role/i, /permission/i, /encryption/i],
  },
  {
    key: "communications",
    label: "Communications & Integrations",
    goal: "External services, notifications, and partner touchpoints are connected and ready for workflow use.",
    patterns: [/notification/i, /\bsms\b/i, /email/i, /calendar/i, /video/i, /gateway/i, /integration/i],
  },
  {
    key: "clinical",
    label: "Core Workflow Delivery",
    goal: "Core user-facing workflows are implemented and usable end-to-end.",
    patterns: [/appointment/i, /patient/i, /diagnosis/i, /consultation/i, /telemedicine/i, /lab/i, /radiology/i],
  },
  {
    key: "finance",
    label: "Financial Operations",
    goal: "Billing, claims, and payment workflows are ready for controlled release.",
    patterns: [/invoice/i, /billing/i, /claim/i, /payment/i, /insurance/i, /partial-payment/i],
  },
  {
    key: "governance",
    label: "Governance & Reporting",
    goal: "Supervisor visibility, auditability, and executive reporting are ready for review.",
    patterns: [/kpi/i, /report/i, /audit/i, /compliance/i, /dashboard/i],
  },
  {
    key: "platform",
    label: "Platform Hardening",
    goal: "Performance, continuity, and operational safeguards are hardened for launch readiness.",
    patterns: [/uptime/i, /reliability/i, /response-time/i, /\bslo\b/i, /continuity/i, /accessibility/i, /localization/i],
  },
];

const EXECUTION_PHASE_RULES: Array<{
  key: string;
  title: string;
  goal: string;
  patterns: RegExp[];
}> = [
  {
    key: "intake",
    title: "Patient Intake & Scheduling",
    goal: "Patient registration, appointment readiness, and access scheduling are established first.",
    patterns: [/registration/i, /national id/i, /appointment/i, /calendar/i, /scheduling/i],
  },
  {
    key: "clinical",
    title: "Clinical Service Delivery",
    goal: "Clinical consultations and provider-facing care workflows are implemented end-to-end.",
    patterns: [/telemedicine/i, /consultation/i, /clinical notes/i, /video consultation/i],
  },
  {
    key: "diagnostics-finance",
    title: "Diagnostics & Financial Operations",
    goal: "Diagnostics, billing, claims, and payment readiness are delivered as one controlled release slice.",
    patterns: [/lab/i, /radiology/i, /billing/i, /invoice/i, /claim/i, /payment/i, /insurance/i],
  },
  {
    key: "portal-communications",
    title: "Patient Portal & Communications",
    goal: "Patient-facing portal journeys, localization, and follow-up communications are ready for use.",
    patterns: [/patient portal/i, /self-service/i, /localization/i, /rtl-ltr/i, /notification/i, /\bsms\b/i, /email/i, /reminder/i],
  },
  {
    key: "reporting",
    title: "Supervisor Reporting",
    goal: "Supervisor KPI visibility and reporting checkpoints are prepared for review.",
    patterns: [/kpi/i, /dashboard/i, /report/i],
  },
  {
    key: "hardening",
    title: "Security & Performance Hardening",
    goal: "Security, continuity, and performance hardening complete the delivery baseline before go-live.",
    patterns: [/multi-factor/i, /\bmfa\b/i, /encryption/i, /audit/i, /uptime/i, /reliability/i, /continuity/i, /response-time/i, /\bslo\b/i],
  },
];

function cleanSpaces(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function normalizeTitle(value: string) {
  return cleanSpaces(value)
    .replace(/â€”/g, "-")
    .replace(/[“”]/g, "\"")
    .replace(/[‘’]/g, "'");
}

export function formatTaskTitle(title?: string | null): string {
  if (!title?.trim()) return "Task";

  let next = normalizeTitle(title);
  for (const [pattern, replacement] of TITLE_OVERRIDES) {
    if (pattern.test(next)) {
      return replacement;
    }
  }

  next = next
    .replace(/^Implement run /i, "Deliver ")
    .replace(/^Implement give /i, "Deliver ")
    .replace(/^Implement /i, "Build ")
    .replace(/^Enforce /i, "Establish ")
    .replace(/^Optimize /i, "Harden ")
    .replace(/\bcreation workflow\b/gi, "workflow")
    .replace(/\bduring workflow\b/gi, "operations")
    .replace(/\bRTL\/LTR\b/gi, "RTL-LTR");

  return cleanSpaces(next);
}

export function formatTaskDescription(description?: string | null): string {
  if (!description?.trim()) return "No description available.";

  let next = normalizeTitle(description);
  next = next
    .replace(/^Actor:\s*Doctor\s*-\s*The Doctor should Allow doctors to /i, "Doctors can ")
    .replace(/^Actor:\s*Doctor\s*-\s*The Doctor should /i, "Doctors can ")
    .replace(/^The system should\s+/i, "")
    .replace(/^Allow doctors to /i, "Doctors can ")
    .replace(/\s+/g, " ")
    .trim();

  return next.charAt(0).toUpperCase() + next.slice(1);
}

export function buildPresentationTasks(tasks: Task[]): Task[] {
  return tasks.map((task) => ({
    ...task,
    title: formatTaskTitle(task.title),
    description: formatTaskDescription(task.description),
  }));
}

function scoreTheme(task: Task, patterns: RegExp[]) {
  const haystack = `${task.title} ${task.description} ${task.skill_required ?? ""} ${task.suggested_owner_role ?? ""}`;
  return patterns.reduce((sum, pattern) => sum + (pattern.test(haystack) ? 1 : 0), 0);
}

function taskText(tasks: Task[]) {
  return tasks.map((task) => formatTaskTitle(task.title)).join(" ");
}

function taskHaystack(task: Task) {
  return `${formatTaskTitle(task.title)} ${formatTaskDescription(task.description)} ${task.skill_required ?? ""} ${task.suggested_owner_role ?? ""}`;
}

function deriveSprintDisplayName(baseName: string, tasks: Task[]) {
  const text = taskText(tasks);

  if (baseName === "Core Workflow Delivery") {
    if (/patient portal|self-service|localization/i.test(text)) return "Patient Experience Delivery";
    if (/lab|radiology|telemedicine|clinical notes/i.test(text)) return "Clinical Service Delivery";
    if (/registration|appointment/i.test(text)) return "Patient Intake & Scheduling";
  }

  if (baseName === "Communications & Integrations") {
    if (/video consultation|calendar synchronization|payment gateway/i.test(text)) return "External Service Integrations";
    if (/sms|email|notification|patient portal/i.test(text)) return "Patient Communications";
  }

  if (baseName === "Governance & Reporting") {
    if (/audit|encryption|multi-factor|response-time|uptime|reliability/i.test(text)) return "Security & Compliance Controls";
    if (/kpi|dashboard|report/i.test(text)) return "Supervisor Reporting";
  }

  if (baseName === "Platform Hardening") {
    if (/response-time|uptime|reliability|continuity/i.test(text)) return "Performance & Continuity Hardening";
    if (/audit|encryption|multi-factor/i.test(text)) return "Security Hardening";
  }

  if (baseName === "Identity & Access Control") {
    if (/multi-factor|encryption|privileged/i.test(text)) return "Identity & Privileged Access";
  }

  return baseName;
}

function deriveSprintDisplayGoal(displayName: string, fallbackGoal: string) {
  return DISPLAY_GOALS[displayName] ?? fallbackGoal;
}

function taskSequence(taskId: string | undefined) {
  if (!taskId) return Number.POSITIVE_INFINITY;
  const match = taskId.match(/(\d+)/);
  return match ? Number.parseInt(match[1], 10) : Number.POSITIVE_INFINITY;
}

function inferSprintTheme(tasks: Task[]) {
  if (!tasks.length) {
    return {
      label: "Delivery Sprint",
      goal: "Delivery work is grouped into a supervisor-ready execution slice.",
      score: 0,
    };
  }

  const ranked = THEME_RULES
    .map((rule) => ({
      ...rule,
      score: tasks.reduce((sum, task) => sum + scoreTheme(task, rule.patterns), 0),
    }))
    .sort((left, right) => right.score - left.score);

  const best = ranked[0];
  if (!best || best.score <= 0) {
    return {
      label: "Delivery Sprint",
      goal: "Delivery work is grouped into a supervisor-ready execution slice.",
      score: 0,
    };
  }

  return {
    label: best.label,
    goal: best.goal,
    score: best.score,
  };
}

export function buildPresentationSprints(
  sprints: SprintSummary[] | undefined,
  tasks: Task[],
): PresentationSprint[] {
  if (!sprints?.length) return [];

  const taskMap = new Map(tasks.map((task) => [task.id, task]));
  const usedNames = new Map<string, number>();

  return sprints.map((sprint) => {
    const sprintTasks = (sprint.tasks ?? [])
      .map((taskId) => taskMap.get(taskId))
      .filter((task): task is Task => Boolean(task));
    const inferred = inferSprintTheme(sprintTasks);
    const rawName = sprint.name?.trim() ? sprint.name : "";
    const themedName = inferred.score > 0 ? deriveSprintDisplayName(inferred.label, sprintTasks) : "";
    const baseName = themedName || rawName || inferred.label;
    const seen = (usedNames.get(baseName) ?? 0) + 1;
    usedNames.set(baseName, seen);
    const displayName = seen > 1 ? `${baseName} ${seen}` : baseName;
    const displayGoal = deriveSprintDisplayGoal(baseName, inferred.goal);

    return {
      ...sprint,
      displayName,
      displayGoal,
    };
  });
}

export function sortPresentationSprints(sprints: PresentationSprint[]) {
  return [...sprints]
    .sort((left, right) => {
      const leftTaskOrder = Math.min(...(left.tasks ?? []).map((taskId) => taskSequence(taskId)));
      const rightTaskOrder = Math.min(...(right.tasks ?? []).map((taskId) => taskSequence(taskId)));
      if (leftTaskOrder !== rightTaskOrder) return leftTaskOrder - rightTaskOrder;
      const leftPriority = COMMITTEE_SPRINT_PRIORITY[left.displayName ?? left.name ?? "Delivery Sprint"] ?? 99;
      const rightPriority = COMMITTEE_SPRINT_PRIORITY[right.displayName ?? right.name ?? "Delivery Sprint"] ?? 99;
      if (leftPriority !== rightPriority) return leftPriority - rightPriority;
      return (left.sprint ?? 0) - (right.sprint ?? 0);
    })
    .map((sprint, index) => ({
      ...sprint,
      displaySprint: index + 1,
    }));
}

export function buildExecutionRoadmap(tasks: Task[]): ExecutionRoadmapPhase[] {
  const used = new Set<string>();

  const phases = EXECUTION_PHASE_RULES
    .map((phase) => {
      const matched = tasks.filter((task) => {
        const id = task.id ?? task.title ?? "";
        if (!id || used.has(id)) return false;
        return phase.patterns.some((pattern) => pattern.test(taskHaystack(task)));
      });

      matched.forEach((task) => {
        const id = task.id ?? task.title ?? "";
        if (id) used.add(id);
      });

      if (!matched.length) return null;

      const totalHours = matched.reduce((sum, task) => sum + (task.estimated_hours ?? 0), 0);
      return {
        key: phase.key,
        title: phase.title,
        goal: phase.goal,
        tasks: matched,
        totalHours,
        durationWeeks: Math.max(1, Math.round(totalHours / 64)),
      };
    })
    .filter((phase): phase is ExecutionRoadmapPhase => Boolean(phase));

  const remaining = tasks.filter((task) => {
    const id = task.id ?? task.title ?? "";
    return id && !used.has(id);
  });

  if (remaining.length) {
    const totalHours = remaining.reduce((sum, task) => sum + (task.estimated_hours ?? 0), 0);
    phases.push({
      key: "remaining",
      title: "Remaining Delivery Work",
      goal: "Unclassified delivery work remains visible for supervisor review and final sequencing.",
      tasks: remaining,
      totalHours,
      durationWeeks: Math.max(1, Math.round(totalHours / 64)),
    });
  }

  return phases;
}
