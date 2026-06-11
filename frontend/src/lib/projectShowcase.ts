import type { AllData, BriefData, Task } from "./api";
import {
  DEMO_ALL_DATA,
  DEMO_BRIEF_DATA,
  DEMO_TASKS,
} from "./demoProject";
import { buildPresentationTasks } from "./presentation";

type CommitteeBriefShape = {
  domain_inference?: string;
  scope_assessment?: string;
  confidence_signal?: string;
  graph_summary?: string;
  assumption_log?: string[];
};

export type ShowcaseStep = {
  id: string;
  title: string;
  stage: string;
};

export type ShowcaseData = {
  title: string;
  domain: string;
  scope: string;
  confidence: string;
  summary: string;
  evidence: string[];
  criticalPath: ShowcaseStep[];
  criticalPathNote: string;
  riskFocus: string[];
  teamRoles: string[];
  sprintLabel: string;
  dataLabel: string;
  isDemo: boolean;
  taskCount: number;
};

function summaryCommitteeBrief(data: AllData | null, brief: BriefData | null): CommitteeBriefShape {
  const summaryBrief = (data?.summary as { committee_brief?: CommitteeBriefShape } | null)?.committee_brief;
  return brief?.committee_brief ?? summaryBrief ?? DEMO_BRIEF_DATA.committee_brief;
}

function findTask(tasks: Task[], taskId: string): Task | undefined {
  return tasks.find((task) => task.id === taskId);
}

function cleanSentence(value: string | undefined, fallback: string): string {
  const text = value?.trim();
  return text ? text : fallback;
}

function normalizeDomainText(projectName: string, domainText: string) {
  if (projectName.toLowerCase().includes("clinic") && domainText.toLowerCase().includes("hospital operations")) {
    return "Likely domain: clinic operations and telemedicine workflow management.";
  }
  return domainText;
}

const WALKTHROUGH_RULES: Array<{ stage: string; patterns: RegExp[] }> = [
  {
    stage: "Patient intake foundation",
    patterns: [/registration/i, /national id/i, /identity/i, /access/i],
  },
  {
    stage: "Appointment operations",
    patterns: [/appointment/i, /schedule/i, /triage/i, /calendar/i],
  },
  {
    stage: "Clinical service delivery",
    patterns: [/telemedicine/i, /consultation/i, /diagnosis/i],
  },
  {
    stage: "Diagnostics and treatment coordination",
    patterns: [/lab/i, /radiology/i, /order tracking/i, /prescription/i],
  },
  {
    stage: "Financial workflow readiness",
    patterns: [/billing/i, /invoice/i, /claim/i, /payment/i, /insurance/i],
  },
  {
    stage: "Patient communication and follow-up",
    patterns: [/notification/i, /\bsms\b/i, /email/i, /portal/i, /reminder/i],
  },
  {
    stage: "Governance and reporting",
    patterns: [/kpi/i, /dashboard/i, /report/i, /analytics/i],
  },
  {
    stage: "Security and resilience controls",
    patterns: [/audit/i, /encryption/i, /uptime/i, /reliability/i, /continuity/i, /response-time/i, /mfa/i, /multi-factor/i],
  },
];

function stageForTask(task: Task) {
  const haystack = `${task.title} ${task.description ?? ""}`;
  const match = WALKTHROUGH_RULES.find((rule) => rule.patterns.some((pattern) => pattern.test(haystack)));
  return match?.stage ?? "Delivery milestone";
}

function buildCriticalPath(tasks: Task[], ids: string[]): ShowcaseStep[] {
  const used = new Set<string>();
  const committeeWalkthrough = WALKTHROUGH_RULES
    .map((rule) => {
      const task = tasks.find((candidate) => {
        if (!candidate.id || used.has(candidate.id)) return false;
        const haystack = `${candidate.title} ${candidate.description ?? ""}`;
        return rule.patterns.some((pattern) => pattern.test(haystack));
      });
      if (!task?.id) return null;
      used.add(task.id);
      return {
        id: task.id,
        title: task.title,
        stage: rule.stage,
      };
    })
    .filter((step): step is ShowcaseStep => Boolean(step));

  if (committeeWalkthrough.length >= 4) {
    return committeeWalkthrough;
  }

  const actual = ids
    .map((taskId) => findTask(tasks, taskId))
    .filter((task): task is Task => Boolean(task))
    .map((task) => ({
      id: task.id,
      title: task.title,
      stage: stageForTask(task),
    }));
  if (actual.length) {
    return actual;
  }
  return ["T001", "T002", "T004", "T005", "T008"].map((taskId) => {
    const task = findTask(DEMO_TASKS, taskId)!;
    return { id: task.id, title: task.title, stage: stageForTask(task) };
  });
}

function buildSummaryText({
  requirementCount,
  taskCount,
  sprintCount,
  totalHours,
  frCount,
  nfrCount,
  criticalPath,
}: {
  requirementCount: number | null;
  taskCount: number;
  sprintCount: number;
  totalHours: number;
  frCount: number;
  nfrCount: number;
  criticalPath: ShowcaseStep[];
}) {
  const lead = requirementCount != null
    ? `${requirementCount} requirements were translated into ${taskCount} structured tasks across ${sprintCount} delivery sprint(s).`
    : `${taskCount} structured tasks are organized across ${sprintCount} delivery sprint(s).`;

  const pathLine = criticalPath.length
    ? `The committee walkthrough moves through ${criticalPath.map((step) => step.stage).join(" -> ")} and highlights the main delivery gates.`
    : "The committee walkthrough is staged to surface the highest-impact delivery gates first.";

  const effortLine = `Estimated effort is ${totalHours} hours with ${frCount} functional and ${nfrCount} non-functional work items.`;

  return `${lead} ${pathLine} ${effortLine}`;
}

function buildScopeText(frCount: number, nfrCount: number, optionalCount: number) {
  const baselineText = optionalCount > 0
    ? `${optionalCount} optional task(s) are separated from the core release baseline.`
    : "All current tasks sit inside the confirmed release baseline.";
  return `${frCount} functional and ${nfrCount} non-functional tasks are balanced across the delivery baseline. ${baselineText}`;
}

function buildConfidenceText(tasks: Task[], criticScore: number) {
  const lowConfidenceCount = tasks.filter((task) => task.confidence !== "high").length;
  if (lowConfidenceCount === 0 && criticScore >= 0.9) {
    return "Planning confidence is high: the task set is structured, review-ready, and free from low-confidence items.";
  }
  if (lowConfidenceCount > 0) {
    return `Planning confidence is moderate: ${lowConfidenceCount} task(s) still need closer review before release.`;
  }
  return "Planning confidence is stable and the delivery plan is ready for supervisor review.";
}

function buildQualityNarrative({
  criticScore,
  riskLevel,
  totalRisks,
}: {
  criticScore: number;
  riskLevel: string;
  totalRisks: number;
}) {
  if (criticScore >= 0.95 && (riskLevel === "critical" || riskLevel === "high")) {
    return `Quality gate passed cleanly; the main watch items are concentrated in ${totalRisks} controlled risk area(s) around security, integration, and performance.`;
  }
  if (criticScore >= 0.9) {
    return `Quality gate passed with strong planning coverage and ${totalRisks} tracked risk area(s).`;
  }
  return `Critic score is ${Math.round(criticScore * 100)}% with ${totalRisks} tracked risk area(s) currently under review.`;
}

export function formatQualityGate(score: number | null | undefined) {
  if (typeof score !== "number") return "Under review";
  if (score >= 0.95) return "Passed";
  if (score >= 0.9) return "High";
  if (score >= 0.8) return "Review";
  return "Needs work";
}

export function buildShowcaseData(data: AllData | null, brief: BriefData | null): ShowcaseData {
  const committeeBrief = summaryCommitteeBrief(data, brief);
  const demoCommitteeBrief = DEMO_BRIEF_DATA.committee_brief;
  const rawTasks = data?.tasks?.tasks?.length ? data.tasks.tasks : DEMO_ALL_DATA.tasks?.tasks ?? [];
  const tasks = buildPresentationTasks(rawTasks);
  const summary = data?.summary ?? DEMO_ALL_DATA.summary;
  const taskCount = tasks.length;
  const frCount = tasks.filter((task) => task.req_type === "FR").length;
  const nfrCount = tasks.filter((task) => task.req_type === "NFR").length;
  const sprintCount = summary?.sprint_plan?.length ?? DEMO_ALL_DATA.summary?.sprint_plan?.length ?? 0;
  const riskLevel = data?.risks?.risk_level ?? DEMO_ALL_DATA.risks?.risk_level ?? "medium";
  const criticScore = summary?.critic?.score ?? DEMO_ALL_DATA.summary?.critic?.score ?? 0.94;
  const totalRisks = data?.risks?.total_risks ?? data?.risks?.risks?.length ?? DEMO_ALL_DATA.risks?.total_risks ?? 0;
  const totalHours = tasks.reduce((sum, task) => sum + (task.estimated_hours ?? 0), 0);
  const optionalCount = summary?.graph_analytics?.optional_task_count ?? tasks.filter((task) => task.optional).length;
  const requirementCount =
    ((summary?.plan_highlights as { requirement_count?: number } | undefined)?.requirement_count)
    ?? null;

  const projectName =
    (summary?.plan_highlights as { project_name?: string } | undefined)?.project_name
    ?? (brief?.plan_highlights as { project_name?: string } | undefined)?.project_name
    ?? "Smart Clinic & Telemedicine Platform";

  const criticalPathIds =
    summary?.graph_analytics?.critical_path?.task_ids
    ?? DEMO_ALL_DATA.summary?.graph_analytics?.critical_path?.task_ids
    ?? [];
  const criticalPath = buildCriticalPath(tasks, criticalPathIds);

  const teamRoles = (brief?.team_allocation ?? summary?.team_allocation ?? DEMO_BRIEF_DATA.team_allocation)
    .slice(0, 4)
    .map((item) => `${item.role} - ${item.focus}`);

  const riskFocus = (brief?.risk_register ?? summary?.risk_register ?? DEMO_BRIEF_DATA.risk_register)
    .slice(0, 3)
    .map((item) => `${item.risk} (${item.task_count} tasks)`);

  return {
    title: projectName,
    domain: normalizeDomainText(
      projectName,
      cleanSentence(committeeBrief.domain_inference, demoCommitteeBrief.domain_inference ?? "Domain inferred from the project brief."),
    ),
    scope: buildScopeText(frCount, nfrCount, optionalCount),
    confidence: buildConfidenceText(tasks, criticScore),
    summary: buildSummaryText({
      requirementCount,
      taskCount,
      sprintCount,
      totalHours,
      frCount,
      nfrCount,
      criticalPath,
    }),
    evidence: [
      `${taskCount} structured tasks covering ${frCount} functional and ${nfrCount} non-functional delivery concerns.`,
      `${sprintCount} sprint(s) staged with a committee-ready walkthrough of the main delivery milestones.`,
      buildQualityNarrative({ criticScore, riskLevel, totalRisks }),
    ],
    criticalPath,
    criticalPathNote: criticalPath.length
      ? `${criticalPath.length} spotlight milestones are shown here for the committee walkthrough. Open the Task Graph for the full dependency network across all ${taskCount} tasks.`
      : `The full dependency network spans ${taskCount} tasks. Open the Task Graph for the detailed view.`,
    riskFocus,
    teamRoles,
    sprintLabel: sprintCount > 0 ? `${sprintCount} sprint delivery roadmap ready` : "Sprint roadmap prepared for committee walkthrough",
    dataLabel: data?.tasks?.tasks?.length ? "Committee plan summary" : "Committee demo preview",
    isDemo: !(data?.tasks?.tasks?.length),
    taskCount,
  };
}
