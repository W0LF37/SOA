import type {
  AllData,
  BriefData,
  MonitorReport,
  PlanSummary,
  RiskReport,
  SprintSummary,
  Task,
  TeamMember,
  TechStackReport,
} from "./api";

export const DEFAULT_PROJECT_SAMPLE_NAME = "Committee Demo";

export const PROJECT_SAMPLES: Record<string, string> = {
  "Committee Demo": `Project Title:
Smart Clinic & Telemedicine Platform

Project Overview:
A bilingual web platform for outpatient clinics that unifies patient intake,
appointment scheduling, telemedicine consultations, lab coordination, billing,
and executive reporting in one secure workspace.

Problem Statement:
Clinic teams currently split their work across paper files, spreadsheets, and
chat messages. This creates appointment conflicts, slow patient onboarding,
missing follow-up tasks, weak auditability, and delayed billing.

Proposed Solution:
Build a role-based digital platform where receptionists, doctors, nurses, lab
staff, finance staff, and supervisors collaborate on the same patient journey
from registration to consultation, payment, and reporting.

Target Users:
- Receptionist
- Doctor
- Nurse
- Lab Staff
- Finance Staff
- Clinic Manager
- Patient

Main Features:
- Register patients using national ID, insurance details, emergency contacts,
  and signed consent forms
- Manage doctor schedules, room availability, triage priority, and appointment
  reminders
- Run telemedicine consultations with structured notes, diagnosis summaries,
  prescriptions, and follow-up tasks
- Create lab and radiology orders, track result status, and attach results to
  the patient record
- Generate invoices, manage insurance claims, record partial payments, and
  monitor unpaid balances
- Provide a bilingual patient portal for appointments, invoices, visit history,
  and post-visit instructions
- Give supervisors KPI dashboards for waiting time, no-show rate, doctor
  utilization, clinic revenue, and patient satisfaction

Integrations:
- SMS and email notifications
- Secure payment gateway
- Video consultation provider
- Calendar synchronization for doctors

Non-Functional Requirements:
- Arabic and English interfaces with consistent terminology
- Role-based access control with MFA for privileged staff
- Encryption for sensitive patient and payment data
- Immutable audit logs for critical clinical and financial actions
- p95 response time below 2 seconds for standard operations
- 99.9% service availability during clinic hours
- Graceful continuity for reception workflows during short internet outages

Expected Deliverables:
The final output should include a task plan, sprint roadmap, dependency graph,
risk register, team allocation view, and a supervisor-ready committee brief.`,
  "Clinic System": `Project Title:
Clinic Management System

Project Overview:
A web-based system to manage clinic operations including patient registration,
appointments, consultations, and billing.

Problem Statement:
Clinic staff currently manage patient records and appointments on paper,
leading to errors, duplicate records, and inefficient scheduling.

Proposed Solution:
Build a unified digital platform where receptionists, doctors, and billing
staff can collaborate on a single patient record.

Target Users:
- Receptionist
- Doctor
- Billing Staff

Main Features:
- Register new patients using national ID and contact details
- Book and manage patient appointments for available doctors
- Allow doctors to view patient history and record diagnosis
- Generate itemized invoices for consultations and lab tests
- Send appointment reminders to patients via email

Expected Benefits:
The system should be fast and reliable to ensure zero downtime during clinic
hours. Patient data should be secure and accessible only to authorized users.

Constraints or Special Notes:
- Must support both Arabic and English languages
- System must respond within two seconds for all standard operations`,
  "University Portal": `Project Title:
University Student Portal

Project Overview:
A web-based platform for course enrollment, grade tracking, tuition payments,
and advisor communication.

Main Features:
- Register and enroll in available courses
- Upload grades and course materials
- Generate tuition invoices and process online payments
- Send automated email notifications for deadlines

Expected Benefits:
The system must be highly available, encrypted, mobile-friendly, and
responsive under peak load.`,
  "Hospital System": `Project Title:
Hospital Management System

Project Overview:
A comprehensive platform for managing patient records, appointments, billing,
and pharmacy inventory.

Main Features:
- Patient registration with national ID and insurance
- Doctor scheduling and appointment booking
- Electronic medical records (EMR)
- Pharmacy stock management and prescriptions
- Billing and insurance claim processing

Non-Functional Requirements:
HIPAA-compliant data security, 99.9% uptime, sub-2s response time.`,
  "E-commerce": `Project Title:
E-Commerce Platform

Project Overview:
An online shopping platform supporting product listings, cart management,
secure checkout, and order tracking.

Main Features:
- Product catalog with search and filters
- Shopping cart and wishlist
- Multi-payment gateway integration
- Order tracking and notifications
- Seller dashboard and inventory management

Non-Functional Requirements:
Scalable to 10,000 concurrent users, PCI-DSS compliant, mobile-first.`,
  "Mobile Banking": `Project Title:
Mobile Banking Application

Project Overview:
A secure mobile app enabling customers to manage accounts, transfer funds,
pay bills, and access financial insights.

Main Features:
- Biometric login and two-factor authentication
- Account balance and transaction history
- Fund transfers and scheduled payments
- Bill payments and QR code transactions
- Spending analytics and budget alerts

Non-Functional Requirements:
Bank-grade encryption, offline capability, PCI-DSS level 1.`,
};

export const DEFAULT_PROJECT_BRIEF = PROJECT_SAMPLES[DEFAULT_PROJECT_SAMPLE_NAME];

export const DEMO_TECH_STACK: TechStackReport = {
  frontend: ["responsive web ui", "i18n localization", "accessibility layer"],
  backend: ["fastapi", "application api", "auth and authorization", "compliance controls"],
  database: ["relational database"],
  devops: ["availability monitoring", "observability", "disaster recovery"],
  external_services: ["payment gateway", "email service", "messaging service", "identity verification"],
  detected_from: "requirements+inferred",
};

export const DEMO_TASKS: Task[] = [
  {
    id: "T001",
    title: "Design clinic operating model and requirements baseline",
    description: "Consolidate patient journey, staff roles, success metrics, and committee scope into a validated delivery baseline.",
    req_type: "FR",
    type_reason: "Defines the core business workflow that anchors all later delivery work.",
    complexity: 2,
    complexity_reason: "Focused analysis with moderate stakeholder alignment effort.",
    dependencies: [],
    source: "line 1",
    estimated_hours: 14,
    estimated_days: 2,
    recommended_team_size: 1,
    skill_required: "Product analysis",
    suggested_owner_role: "Product Manager",
    risks: ["stakeholder alignment"],
    estimation_breakdown: {
      base_hours: 12,
      type_multiplier: 1.0,
      integration_overhead: 2,
      rag_adjustment_pct: 8,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
  {
    id: "T002",
    title: "Implement patient identity, RBAC, and staff access foundation",
    description: "Create secure patient profiles, clinic staff roles, privileged access flows, and MFA-ready account controls.",
    req_type: "FR",
    type_reason: "Supports a core user-facing access workflow across every role.",
    complexity: 4,
    complexity_reason: "Touches identity, authorization, and multiple user journeys.",
    dependencies: ["T001"],
    source: "line 2",
    estimated_hours: 40,
    estimated_days: 5,
    recommended_team_size: 2,
    skill_required: "Backend security",
    suggested_owner_role: "Backend Engineer",
    risks: ["security", "access control"],
    estimation_breakdown: {
      base_hours: 28,
      type_multiplier: 1.2,
      integration_overhead: 6,
      rag_adjustment_pct: 10,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
  {
    id: "T003",
    title: "Build scheduling, triage, and availability orchestration",
    description: "Coordinate doctor calendars, room usage, triage priority, and reminder timing for clinic and telemedicine sessions.",
    req_type: "FR",
    type_reason: "Represents a central scheduling workflow with direct end-user value.",
    complexity: 4,
    complexity_reason: "Includes coordination logic, business rules, and availability conflicts.",
    dependencies: ["T001"],
    source: "line 3",
    estimated_hours: 36,
    estimated_days: 5,
    recommended_team_size: 2,
    skill_required: "Workflow design",
    suggested_owner_role: "Full-Stack Engineer",
    risks: ["schedule pressure", "dependency chain"],
    estimation_breakdown: {
      base_hours: 26,
      type_multiplier: 1.15,
      integration_overhead: 6,
      rag_adjustment_pct: 8,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
  {
    id: "T004",
    title: "Deliver telemedicine consultation and structured EMR workspace",
    description: "Enable remote and on-site consultations with SOAP notes, prescriptions, follow-up tasks, and shared patient context.",
    req_type: "FR",
    type_reason: "Implements the main clinical workflow expected by doctors and patients.",
    complexity: 5,
    complexity_reason: "Spans clinical UX, shared records, and high-risk workflow integration.",
    dependencies: ["T002", "T003"],
    source: "line 4",
    estimated_hours: 56,
    estimated_days: 7,
    recommended_team_size: 2,
    skill_required: "Clinical workflow implementation",
    suggested_owner_role: "Full-Stack Engineer",
    risks: ["integration", "quality signal"],
    estimation_breakdown: {
      base_hours: 38,
      type_multiplier: 1.2,
      integration_overhead: 10,
      rag_adjustment_pct: 12,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
  {
    id: "T005",
    title: "Integrate lab, prescription, billing, and insurance operations",
    description: "Connect clinical decisions to lab orders, e-prescriptions, invoices, claims, and payment reconciliation.",
    req_type: "FR",
    type_reason: "Supports essential operational workflows across care and finance.",
    complexity: 5,
    complexity_reason: "Combines multiple downstream systems and heavy business rules.",
    dependencies: ["T004"],
    source: "line 5",
    estimated_hours: 48,
    estimated_days: 6,
    recommended_team_size: 2,
    skill_required: "Systems integration",
    suggested_owner_role: "Backend Engineer",
    risks: ["third-party dependency", "billing accuracy"],
    estimation_breakdown: {
      base_hours: 34,
      type_multiplier: 1.15,
      integration_overhead: 9,
      rag_adjustment_pct: 11,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
  {
    id: "T006",
    title: "Launch bilingual patient portal and notification journeys",
    description: "Provide Arabic and English patient self-service for appointments, invoices, visit history, reminders, and care instructions.",
    req_type: "FR",
    type_reason: "Delivers a clear patient-facing workflow with direct service value.",
    complexity: 3,
    complexity_reason: "Moderate UI scope with localization and notification dependencies.",
    dependencies: ["T002", "T003"],
    source: "line 6",
    estimated_hours: 28,
    estimated_days: 4,
    recommended_team_size: 2,
    skill_required: "Frontend product delivery",
    suggested_owner_role: "Frontend Engineer",
    risks: ["localization", "notification reliability"],
    estimation_breakdown: {
      base_hours: 20,
      type_multiplier: 1.1,
      integration_overhead: 4,
      rag_adjustment_pct: 8,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
  {
    id: "T007",
    title: "Enforce encryption, audit logging, and continuity controls",
    description: "Harden the platform with data encryption, immutable audit events, backup recovery, and short-outage continuity for reception workflows.",
    req_type: "NFR",
    type_reason: "Captures security and reliability constraints that protect the delivery baseline.",
    complexity: 4,
    complexity_reason: "Cross-cutting implementation with compliance and resilience impact.",
    dependencies: ["T002"],
    source: "line 7",
    estimated_hours: 32,
    estimated_days: 4,
    recommended_team_size: 1,
    skill_required: "Security engineering",
    suggested_owner_role: "Platform Engineer",
    risks: ["compliance", "recovery"],
    estimation_breakdown: {
      base_hours: 24,
      type_multiplier: 1.1,
      integration_overhead: 5,
      rag_adjustment_pct: 7,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
  {
    id: "T008",
    title: "Publish executive analytics and committee-ready reporting",
    description: "Surface utilization, waiting time, revenue, and satisfaction insights with dashboards and exportable committee materials.",
    req_type: "NFR",
    type_reason: "Represents reporting and governance quality requirements for decision-makers.",
    complexity: 3,
    complexity_reason: "Moderate reporting scope with multiple upstream dependencies.",
    dependencies: ["T004", "T005", "T006", "T007"],
    source: "line 8",
    estimated_hours: 24,
    estimated_days: 3,
    recommended_team_size: 1,
    skill_required: "Analytics delivery",
    suggested_owner_role: "Data / BI Engineer",
    risks: ["data quality", "schedule pressure"],
    estimation_breakdown: {
      base_hours: 18,
      type_multiplier: 1.05,
      integration_overhead: 4,
      rag_adjustment_pct: 6,
      confidence: "high",
    },
    optional: false,
    confidence: "high",
  },
];

export const DEMO_SPRINT_PLAN: SprintSummary[] = [
  {
    sprint: 1,
    name: "Foundation and Governance",
    goal: "Lock the operating model, secure identities, and stabilize scheduling rules.",
    tasks: ["T001", "T002", "T003"],
    total_estimated_hours: 90,
    total_points: 10,
    duration_weeks: 2,
    owner_roles: ["Product Manager", "Backend Engineer", "Full-Stack Engineer"],
    focus_themes: ["requirements intake", "access control", "core workflows"],
  },
  {
    sprint: 2,
    name: "Care Delivery Experience",
    goal: "Enable consultations, EMR handling, and the bilingual patient-facing experience.",
    tasks: ["T004", "T006"],
    total_estimated_hours: 84,
    total_points: 8,
    duration_weeks: 2,
    owner_roles: ["Full-Stack Engineer", "Frontend Engineer"],
    focus_themes: ["core workflows", "localization", "communications"],
  },
  {
    sprint: 3,
    name: "Financial and Security Hardening",
    goal: "Connect billing operations while enforcing security and recovery controls.",
    tasks: ["T005", "T007"],
    total_estimated_hours: 80,
    total_points: 9,
    duration_weeks: 2,
    owner_roles: ["Backend Engineer", "Platform Engineer"],
    focus_themes: ["integrations", "security", "compliance"],
  },
  {
    sprint: 4,
    name: "Committee Reporting and Go-Live Readiness",
    goal: "Deliver leadership reporting and a final committee-ready showcase.",
    tasks: ["T008"],
    total_estimated_hours: 24,
    total_points: 3,
    duration_weeks: 1,
    owner_roles: ["Data / BI Engineer"],
    focus_themes: ["reporting", "dashboard visibility"],
  },
];

export const DEMO_TEAM_ALLOCATION: TeamMember[] = [
  {
    role: "Backend Engineer",
    task_ids: ["T002", "T005"],
    task_count: 2,
    estimated_hours: 88,
    focus: "identity, integrations, billing operations",
  },
  {
    role: "Full-Stack Engineer",
    task_ids: ["T003", "T004"],
    task_count: 2,
    estimated_hours: 92,
    focus: "clinical workflow orchestration and care delivery",
  },
  {
    role: "Frontend Engineer",
    task_ids: ["T006"],
    task_count: 1,
    estimated_hours: 28,
    focus: "patient portal and bilingual experience",
  },
  {
    role: "Platform Engineer",
    task_ids: ["T007"],
    task_count: 1,
    estimated_hours: 32,
    focus: "security, resilience, and auditability",
  },
  {
    role: "Data / BI Engineer",
    task_ids: ["T008"],
    task_count: 1,
    estimated_hours: 24,
    focus: "executive reporting and KPI dashboards",
  },
];

export const DEMO_RISK_REPORT: RiskReport = {
  risk_level: "medium",
  risk_score: 0.43,
  total_risks: 4,
  generated_at: "2026-05-27T13:00:00Z",
  mitigations: [
    "Finalize third-party integration contracts before Sprint 3.",
    "Run security design review before clinical data goes live.",
    "Protect Sprint 2 scope from late committee change requests.",
  ],
  risks: [
    {
      category: "dependency",
      severity: "high",
      message: "The EMR workspace and financial workflows depend on a stable identity and scheduling foundation, so delays in Sprint 1 will ripple through the whole plan.",
      mitigation: "Time-box Sprint 1 acceptance criteria and freeze high-risk workflow rules before development starts.",
      affected_tasks: ["T002", "T003", "T004", "T005"],
      source: "rule",
    },
    {
      category: "integration",
      severity: "medium",
      message: "Billing, insurance, messaging, and telemedicine providers introduce cross-team coordination risk in the middle of the delivery plan.",
      mitigation: "Secure sandbox access and contract assumptions before Sprint 3 begins.",
      affected_tasks: ["T004", "T005", "T006"],
      source: "rule",
    },
    {
      category: "security",
      severity: "medium",
      message: "Clinical and payment data raise compliance exposure if encryption, audit logging, and privileged access boundaries land late.",
      mitigation: "Treat T007 as a release gate and review it alongside architecture decisions.",
      affected_tasks: ["T002", "T007"],
      source: "rule",
    },
    {
      category: "schedule",
      severity: "low",
      message: "Executive reporting depends on nearly every upstream stream, so committee-report polish can compress near the end of the schedule.",
      mitigation: "Prepare dashboard scaffolding earlier and reserve buffer in Sprint 4.",
      affected_tasks: ["T008"],
      source: "rule",
    },
  ],
};

export const DEMO_BRIEF_DATA: BriefData = {
  committee_brief: {
    domain_inference: "Likely domain: hospital operations and clinical workflow management.",
    scope_assessment: "Scope balances patient-facing workflows, clinic operations, finance, and governance with 6 functional tasks and 2 non-functional control tasks.",
    confidence_signal: "Planning confidence is high: the sample brief contains clear actors, measurable constraints, and a stable implementation order.",
    graph_summary: "This committee demo presents a clinic modernization program that starts with governance and identity, then moves through scheduling, consultation, financial integration, and finally executive reporting. The strongest path runs through identity, EMR delivery, and billing integration before dashboards can be trusted for leadership review.",
    ambiguity_register: [],
    assumption_log: [
      "Role-based access boundaries are required because the brief names multiple clinical and operational actors.",
      "Delivery was split into four sprints to make the committee narrative easy to defend.",
      "Operational continuity was modeled as a release gate because the brief explicitly mentions short internet outages.",
    ],
  },
  team_allocation: DEMO_TEAM_ALLOCATION,
  risk_register: [
    { risk: "integration sequencing", task_count: 3, task_ids: ["T004", "T005", "T006"] },
    { risk: "security and compliance hardening", task_count: 2, task_ids: ["T002", "T007"] },
    { risk: "committee reporting latency", task_count: 1, task_ids: ["T008"] },
  ],
  effort_summary: {
    total_estimated_hours: 278,
    total_estimated_days: 35,
    fr_estimated_hours: 222,
    nfr_estimated_hours: 56,
  },
  plan_highlights: {
    project_name: "Smart Clinic & Telemedicine Platform",
    atomic_task_ratio: 1.33,
    domain: "clinic operations",
    likely_domain: "clinical operations",
  },
  admin_review: {
    status: "empty",
    total_flagged: 0,
    tasks_final_file: "data/processed/tasks_final.json",
  },
  critic: {
    score: 0.94,
    status: "approved",
  },
  generated_at: "2026-05-27T13:00:00Z",
  model: "ai-project-manager-planner",
  generation_mode: "committee_demo_preview",
};

export const DEMO_MONITOR_REPORT: MonitorReport = {
  overall_progress: 0.58,
  tasks_completed: 3,
  tasks_in_progress: 2,
  tasks_not_started: 3,
  tasks_needs_review: 1,
  commits_analyzed: 18,
};

export const DEMO_PLAN_SUMMARY: PlanSummary = {
  generated_at: "2026-05-27T13:00:00Z",
  model: "ai-project-manager-planner",
  provider: "ollama",
  generation_mode: "committee_demo_preview",
  llm_used: true,
  llm_attempted: true,
  llm_accepted: true,
  llm_model: "ai-project-manager-planner",
  used_fallback: false,
  fallback_reason: null,
  retrieved_kb_context: "",
  kb_document_count: 12,
  llm_planning_trace: {
    role: "LLM Planning Reasoner",
    attempted: true,
    accepted: true,
    used_fallback: false,
    fallback_reason: null,
    kb_enabled: true,
    retrieved_kb_context_chars: 0,
    kb_document_count: 12,
  },
  critic: {
    status: "approved",
    score: 0.94,
    issues_count: 1,
    report_file: "data/processed/critic_report.json",
  },
  input_file: "data/raw/docs/project_brief_sample.txt",
  tasks_file: "data/processed/tasks.json",
  graph_file: "storage/graph/dependency_graph.json",
  pipeline_config: {
    allow_fallback: true,
    allow_decomposition: true,
    force_fallback: false,
    use_kb: true,
  },
  plan_highlights: {
    project_name: "Smart Clinic & Telemedicine Platform",
    atomic_task_ratio: 1.33,
    domain: "clinic operations",
    likely_domain: "clinical operations",
    committee_brief: DEMO_BRIEF_DATA.committee_brief,
  },
  effort_summary: DEMO_BRIEF_DATA.effort_summary,
  team_allocation: DEMO_TEAM_ALLOCATION,
  risk_register: DEMO_BRIEF_DATA.risk_register,
  admin_review: {
    status: "empty",
    total_flagged: 0,
    queue_file: "data/processed/admin_review_queue.json",
    tasks_final_file: "data/processed/tasks_final.json",
  },
  graph_analytics: {
    fr_count: 6,
    nfr_count: 2,
    optional_task_count: 0,
    critical_path: {
      task_ids: ["T001", "T002", "T004", "T005", "T008"],
    },
  },
  sprint_plan: DEMO_SPRINT_PLAN,
};

export const DEMO_ALL_DATA: AllData = {
  tasks: {
    tasks: DEMO_TASKS,
    tech_stack: DEMO_TECH_STACK,
  },
  summary: DEMO_PLAN_SUMMARY,
  risks: DEMO_RISK_REPORT,
  graph: null,
  monitor: DEMO_MONITOR_REPORT,
};
