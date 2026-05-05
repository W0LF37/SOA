# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**AI Project Manager** is a multi-agent local AI system that converts a project brief into a structured execution plan: tasks, dependencies, effort estimates, sprint schedules, risk indicators, and a committee brief. Everything runs locally via Ollama — no paid APIs.

Two roles: **Student** (submits briefs, tracks task progress, rates tasks) and **Supervisor** (reviews tasks in Admin Review, approves/rejects plan via Chat, exports committee brief). Role separation is enforced via a login page — not a dropdown.

## Commands

### Start Everything

```bash
START_FULL.BAT     # Windows: starts Ollama + FastAPI (8000) + React (5173), opens browser
```

### Backend

```bash
python run_api.py                          # FastAPI on localhost:8000 (no reload)
python -m src.pipelines.run_all            # Full pipeline + evaluation
python -m src.pipelines.doc_to_tasks       # Planning pipeline only
python -m src.pipelines.doc_to_tasks --input data/raw/docs/project_brief_sample.txt --force-fallback
python -m src.pipelines.doc_to_tasks --no-force-fallback   # Use LLM (requires Ollama running)
python -m src.kb.seed_cli                  # Seed ChromaDB knowledge base
python -m src.pipelines.evaluate           # Evaluate against ground truth (rule-based forced)
python -m src.pipelines.evaluate --ablation  # Run multi-condition ablation study
```

### Frontend

```bash
cd frontend
npm run dev        # Vite dev server on localhost:5173
npm run build      # tsc + vite build (catches TypeScript errors)
npm run lint       # eslint
```

### Tests

```bash
pytest tests/                              # All tests
pytest tests/test_planner_agent.py        # Single file
pytest tests/ -k "critic"                 # Filter by name
```

Tests use `unittest.TestCase` with fake/recording LLM clients (`FakeLLMClient`, `RecordingLLMClient`) — no real Ollama needed.

### Ollama Model Setup (first time)

Place `Qwen3.5-9B-Q5_K_M.gguf` in `models/`, then:

```bash
ollama create ai-project-manager-planner -f models/Modelfile
ollama serve
```

The Modelfile sets `temperature=0`, `num_ctx=4096`, enforces JSON-only output, and stops on `<|im_end|>` / ` ``` `.

### API Docs

```text
http://localhost:8000/api/docs     # Swagger UI
http://localhost:8000/api/redoc   # ReDoc
```

## Architecture

### Auth & Role System

Login is in `frontend/src/pages/LoginPage.tsx` with hardcoded demo credentials:

- **Student**: ID `STU-2024` + Name `Ahmed Khalid` + password `student123` (3 fields)
- **Supervisor**: code `SUPER-ADM` + password `supervisor123` (2 fields)

Session stored in `localStorage` under key `critiplan_session` as `{ loggedIn, role, name }`.

`frontend/src/lib/store.ts` — Zustand store exposing `auth`, `login(session)`, `logout()`, `data`, `refreshAll()`. The `role` field is derived exclusively from `login()` — never set it directly. `refreshAll()` calls `/api/data/all` and populates all data slices including `data.tasks.tech_stack`.

`frontend/src/App.tsx` wraps all routes in `ProtectedRoute` (redirects to `/login` if `!auth?.loggedIn`). When `role === "Student"`, `AppShell` renders `<StudentWorkspace />` as full-page (no sidebar). When `role === "Supervisor"`, it renders sidebar + standard `<Routes>`. The Sidebar polls `/api/chat/messages` every 10 seconds and shows an unread badge on the Communication link when messages from the other role arrived in the last 5 minutes.

### Student Flow (`pages/StudentWorkspace.tsx`)

Three-step wizard controlled by `WizardStep = "input" | "analyzing" | "results"`:

1. **input** — textarea with example chips, fires `runPipeline()` on submit
2. **analyzing** — SSE stream from `/api/pipeline/events`, maps log keywords to 6 pipeline stages. Detects `"fallback"` / `"rule-based"` / `"ollama not"` to show yellow warning banner.
3. **results** — metric cards, progress bar, detected tech stack badges, sprint summary, task cards with expand/collapse

Expanded task cards show: `type_reason` + `complexity_reason` explanation panels, star rating (1–5 via `/api/feedback/task`), status buttons (`Todo/Doing/Done` via `/api/progress/update`), and "Ask AI" button opening `ExplainPopup`.

State transitions: `"input"` → `"analyzing"` on generate, `"analyzing"` → `"results"` on SSE `complete` event. If tasks already exist in the store on mount, starts at `"results"`.

**SSE resilience**: The `"analyzing"` step has two fallbacks in case the `complete` event is missed: (1) `heartbeat` listener — if a heartbeat arrives with `status: "completed"`, triggers the same transition logic; (2) a `useEffect` that starts a 2-second timer once all 6 stages enter `doneStages`, then forces `refreshAll()` + `setStep("results")`. This prevents the UI from getting stuck with all stages green but the wizard never advancing.

### Pipeline Stages (`src/pipelines/doc_to_tasks.py`)

Core function: `run_doc_to_tasks_pipeline()`. Runs sequentially:

```text
Input Brief
  → BriefParser / TemplateParser          (src/parsers/)
  → PlannerAgent + OllamaClient           (src/agents/planner.py, src/llm/ollama_client.py)
  → TechStackReport attached              (PlannerAgent._detect_tech_stack → task_list.tech_stack)
  → EffortEstimator                       (src/services/effort_estimator.py)
  → CriticAgent(llm_client=llm_client)   (src/agents/critic.py)
  → DependencyGraph (NetworkX DAG)        (src/graph/dependency_graph.py)
  → SprintPlanner + BriefGenerator        (src/services/)
  → RiskAnalyzer(llm_client=llm_client)  (src/agents/risk_analyzer.py)
  → Writes JSON outputs to data/processed/
```

If `critic.status == "rejected"`, the pipeline exits. `force_fallback` mode uses rule-based decomposition only (no LLM call).

**BriefParser** (`src/parsers/brief_parser.py`) — Section headers must appear on their own line ending with `:` (e.g., `Non-Functional Requirements:`). Bullet content uses `-`, `*`, or `1.` prefixes. For sections that contain comma/semicolon-separated plain text (e.g., `Bank-grade encryption, offline capability, PCI-DSS level 1.`), `_extract_items()` splits on `,`/`;` as a fallback — use it instead of `_extract_bullets()` for NFR and Constraints sections. `_is_nfr()` determines whether a plain-text item should generate an NFR task; extend `_NFR_KEYWORDS` when adding new domains.

### Agent Logic

**PlannerAgent** (`src/agents/planner.py`) — Rule-based decomposition first, LLM second. Sets `type_reason` (why FR vs NFR) and `complexity_reason` (why complexity 1–5) on every task. Tracks `last_used_fallback`. Supports `allow_decomposition`. The `_detect_tech_stack(text)` classmethod does keyword scanning across 5 categories (frontend, backend, database, devops, external_services) and returns a dict that the pipeline wraps into `TechStackReport` and attaches to `TaskList`.

`_propagate_nfr_constraints()` adds dependency edges from NFR tasks to FR tasks they constrain. Rules by NFR semantic tag:

- `security` NFR → blocks FR tasks with tags `auth`, `crud`, `data_management`, `reporting`, or matching `transfer/payment/transaction/financial` keywords
- `offline_operation` NFR → blocks FR tasks with tag `integration` (external APIs/sync), and FR tasks touching financial data (balance, transfer, payment, statement) unless they are public/help content
- `compliance` NFR (PCI-DSS/GDPR/HIPAA/ISO) → blocks non-audit FR tasks with tags `auth`, `crud`, `reporting`, or financial/banking keywords; audit-control NFRs are excluded from this rule
- `general` tag assigned only when no other semantic tag matches — prevents over-linking

`_extract_semantic_tags()` assigns tags: `auth`, `crud`, `view`, `integration`, `compliance`, `security`, `offline_operation`. Domain-specific patterns cover financial verbs (pay, transfer, withdraw, deposit) and banking nouns (balance, statement, analytics). Regex patterns use `\w*` suffix (not `\b`) for stems like `authenticat\w*` to match "authentication", "authenticated", etc.

**CriticAgent** (`src/agents/critic.py`) — Layer 1: business rules (cycle detection via DFS, duplicate IDs, FR/NFR ratio, complexity outliers). Layer 2: LLM holistic review — wired via `llm_client` passed from the pipeline. Penalty: error=0.20, warning=0.05, info=0.01. Rejects if score < 0.50.

**RiskAnalyzer** (`src/agents/risk_analyzer.py`) — Six rule-based categories: bottleneck, complexity, schedule, dependency, resource, quality. `_layer_llm()` proposes novel risks not covered by rules; these are tagged `source="llm"`.

**MonitorAgent** (`src/agents/monitor.py`) — Two-layer commit matching:

- Semantic: SentenceTransformer `all-MiniLM-L6-v2`, threshold `0.65`. Commits with a title shorter than 10 characters are treated as noise and skip semantic matching.
- Keyword fallback: meaningful words from task title matched against commit message + changed files.

Status inference from matched commits:

- 0 matches → `not_started`
- 1 match + done-keywords → `completed` (estimate 1.0)
- 1 match + recent (≤14 days, no done-keywords) → `in_progress` (estimate 0.5)
- 1 match + stale (>14 days, no done-keywords) → `in_progress` (estimate 0.3)
- 2 matches + done-keywords → `completed` (estimate 1.0)
- 2 matches, no done-keywords → `in_progress` (estimate 0.7)
- 3+ matches → `completed` regardless of keywords (volume signals completion)

Requires a real git repo path; pass `commits=[...]` directly for testing.

### Output Files (`data/processed/`)

| File | Contents |
| ---- | -------- |
| `tasks.json` | TaskList — tasks with `type_reason`, `complexity_reason`; includes `tech_stack` (TechStackReport) |
| `tasks_final.json` | TaskList after Admin Review decisions applied |
| `plan_summary.json` | Sprint plan, graph analytics, effort, LLM metadata, critic score |
| `critic_report.json` | Validation score and issues |
| `risk_report.json` | Risk indicators by severity (rule-based + LLM-sourced) |
| `admin_review_queue.json` | Low-confidence tasks flagged for human review |
| `admin_review_decisions.json` | Supervisor decisions with notes per task |
| `task_feedback.json` | Student star ratings (`{ entries: [{task_id, rating, comment, timestamp}] }`) |
| `task_progress.json` | Student task statuses (`not_started / in_progress / completed`) |
| `storage/graph/dependency_graph.json` | NetworkX node-link format DAG |

### Backend (`src/`)

**FastAPI app** (`src/api/main.py`) — CORS allows `localhost:5173` and `localhost:8501`. Swagger at `/api/docs`, ReDoc at `/api/redoc`. All routers:

| Prefix | Router | Purpose |
| ------ | ------ | ------- |
| `/api/data/*` | `data.py` | Serves processed JSON files |
| `/api/data/tech-stack` | `data.py` | Returns `tech_stack` field from `tasks.json` |
| `/api/pipeline/*` | `pipeline.py` | Runs pipeline in background thread, SSE via `GET /events` |
| `/api/monitor/*` | `monitor.py` | Git progress tracking |
| `/api/chat/*` | `chat.py` | Student/supervisor messaging + plan approve/reject |
| `/api/admin/*` | `admin.py` | Admin Review queue — flagged task decisions |
| `/api/evaluate/*` | `evaluate.py` | Ground truth evaluation; `GET /results` returns `{report, ablation, running}` |
| `/api/kb/*` | `kb.py` | Knowledge base browser |
| `/api/ai/*` | `ai_explain.py` | AI self-explanation (LLM per task/risk/critic) |
| `/api/feedback/*` | `feedback.py` | Student task ratings (POST /task, GET /summary) |
| `/api/progress/*` | `progress.py` | Student task status tracking (POST /update, GET /summary) |
| `/api/export/*` | `export.py` | Excel export of tasks (GET /tasks → .xlsx via openpyxl) |

**Pydantic schemas** (`src/core/schemas.py`):

- `Task` — `id` (T\d{3}), `req_type` (FR/NFR), `type_reason`, `complexity` (1–5), `complexity_reason`, `dependencies`, `confidence` (high/medium/low), `optional`
- `TechStackReport` — `frontend`, `backend`, `database`, `devops`, `external_services` (all `list[str]`), `detected_from`
- `TaskList` — validates no duplicate IDs, no unknown deps, no self-deps; has optional `tech_stack: TechStackReport | None`
- `CriticReport` — status (approved/needs_revision/rejected), score 0–1, issues list
- `RiskItem` — category, severity, message, affected_tasks, mitigation, `source` (rule or "llm")
- `RiskReport` — risk_level, risk_score, list of RiskItem
- `MonitorReport` / `TaskProgress` — git-based progress tracking
- `CommitInfo` — sha, message, author, date, files_changed

**LLM client** (`src/llm/ollama_client.py`):

- Calls `http://localhost:11434` — default model `ai-project-manager-planner` (Qwen 3.5-9B Q5_K_M)
- Temperature: 0, timeout: 300s, context: 4096 tokens
- Strips `<think>` blocks and code fences from output
- Falls back to smaller context windows on OOM: `[4096, 3072, 2048, 1536, 1024]`
- Env vars: `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_NUM_CTX`, `OLLAMA_MAX_NUM_PREDICT`

**Knowledge Base** (`src/kb/`):

- ChromaDB at `storage/chroma/`, collection `pm_knowledge`
- Embeddings: SentenceTransformer `all-MiniLM-L6-v2`
- 66 documents across 4 categories: `historical` (Desharnais/Maxwell datasets), `pattern` (task-level Jones baselines), `cocomo` (COCOMO II calibration), `planning_example` (few-shot domain templates for LLM prompt injection)
- Used by EffortEstimator for RAG-calibrated hour estimates (blended: 65% rule / 35% KB for C1–C2; 30/70 for C3+)
- Planning examples are injected into the PlannerAgent LLM prompt as few-shot context (top 2 by domain relevance)
- **CRITICAL**: Always use `get_kb()` from `src.kb.vector_store` — never instantiate `KnowledgeBase()` directly. ChromaDB 1.x Rust bindings break when multiple `PersistentClient` instances open the same database concurrently (e.g., `/api/kb/stats` polling + pipeline running). `get_kb()` returns a module-level singleton. `reset_kb()` clears it (used on error recovery).

**DependencyGraph** (`src/graph/dependency_graph.py`):

- Edge direction: `dependency → task` (A→B means "A must finish before B")
- Edge weight = destination task complexity
- Computes: critical path (longest complexity-weighted path), bottlenecks (highest out-degree), parallel groups (topological generations)

### Frontend (`frontend/src/`)

**State**: `lib/store.ts` — `useAppStore` holds `data`, `brief`, `evaluation`, `kbStats`, `auth`, `role`. Call `refreshAll()` to reload pipeline outputs. `data.tasks.tech_stack` carries the `TechStackReport` from the last pipeline run.

**API client**: `lib/api.ts` — axios to `http://localhost:8000/api` (override with `VITE_API_BASE_URL`). All API functions and response types are defined here, including `TechStackReport` and the updated `AllData` type (`tasks: { tasks?: Task[]; tech_stack?: TechStackReport }`). `explainItem()` has a 90s timeout.

**Styling**: Pages use inline `style={{}}` objects (not Tailwind), except `BriefPage.tsx` which uses Tailwind. `index.css` contains global dark-theme classes (`badge-blue`, `badge-orange`, `primary-btn`, `terminal-window`, `metric-card`, `skeleton`, etc.), `*:focus-visible` outline ring, icon-only sidebar collapse at 900px, and `@media print` styles for PDF export.

**Graph page** (`GraphPage.tsx`) — uses `@xyflow/react` v12. Edges come from `task.dependencies`, not `dependency_graph.json`. The graph JSON is only used for critical path IDs.

**Supervisor-only pages** (rendered only when `role === "Supervisor"` in AppShell's `<Routes>`): Dashboard, PlanPage (read-only task overview), GanttPage, GraphPage, MonitorPage, RisksPage, ChatPage, BriefPage, AdminReviewPage, KBPage, EvaluatePage.

PlanPage has an early-return supervisor branch: shows metric cards (task count, hours, critic score) and links to Dashboard/Chat. Students never see this branch — they always get `StudentWorkspace`.

**EvaluatePage** — Shows score rings (overall, pass rate, coverage, complexity balance, dependency), bar chart comparing F1-FR vs F1-NFR per sample, metrics table with MMRE/PRED(25)/Coverage per sample, LLM vs Rule-Based comparison card, and an ablation table when `ablation_report.json` exists. The API response from `GET /api/evaluate/results` is `{ report, ablation, running }` — `ablation` is null if the file doesn't exist yet.

### Evaluation Pipeline (`src/pipelines/evaluate.py`)

**Critical design**: `run_evaluation()` always uses `FallbackOnlyClient` — a stub that raises `RuntimeError` to force the planner into rule-based mode. This ensures benchmark reproducibility without Ollama. The `force_fallback=True` default applies to all 20 ground truth samples.

To measure LLM contribution, pass a real `llm_client` to `run_sample()` directly (this replaces `FallbackOnlyClient`). The `--ablation` command does this for you across all conditions.

**Ground truth fields that unlock specific metrics** (`data/evaluation/ground_truth.json`):

| Field | Metric unlocked | Notes |
| ----- | --------------- | ----- |
| `actual_hours_per_task` | MMRE + PRED(25) | List of ground-truth hours aligned to task order |
| `task_classifications` | F1-FR + F1-NFR | `[{title_fragment, expected_type}]`; without this, F1 returns **-1.0** (not 0) |
| `expected_classifications` | classification_score | `{FR: float, NFR: float}` ratio target |
| `has_dependency_chain` | dependency check | Boolean |

**Ablation study** (`run_ablation()`): compares pipeline conditions across all samples and writes `data/evaluation/ablation_report.json`. The `GET /api/evaluate/results` endpoint serves this as the `ablation` field. Conditions in the report use keys `R`, `K`, `L`, `Z` (or legacy `A`, `D`).

**Key `EvaluationResult` fields**: `sample_id`, `passed`, `task_count`, `fr_count`, `nfr_count`, `coverage_score`, `classification_score`, `complexity_score`, `dependency_score`, `overall_score`, `mmre`, `pred25`, `f1_fr`, `f1_nfr`, `used_fallback`, `fallback_reason`.

### Admin Review Flow

`/admin` shows tasks flagged as low-confidence or optional (`admin_review_queue.json`). Supervisor can: **Approved**, **Edited** (modify title + optional note), **Rejected**, **Skipped**, or **Approve All**. After submission: rejected task IDs are removed from dependency lists of remaining tasks; results written to `tasks_final.json` and `admin_review_decisions.json`.

**Admin Review vs ChatPage**: Admin Review acts on individual flagged tasks. ChatPage is for overall plan approval/rejection with comments. Only Supervisors see the "Clear History" button in ChatPage.

### AI Self-Explanation (`/api/ai/explain`)

`POST /api/ai/explain` — `src/api/routers/ai_explain.py`

Reads relevant `data/processed/*.json`, builds a focused prompt, calls Ollama directly via `requests.post` with `temperature=0.3, num_ctx=2048, num_predict=512`. Three context types: `"task"` (by id from tasks.json), `"risk"` (by integer index from risk_report.json), `"critic"` (from plan_summary.json).

`ExplainPopup` (`frontend/src/components/ExplainPopup.tsx`) — used from both StudentWorkspace (per-task) and Dashboard (per-task in the task table).

## Runtime Environment

- **Python 3.14** — key packages: `chromadb 1.5.8`, `fastapi 0.136`, `sentence-transformers 5.4`
- **ChromaDB 1.x** uses a Rust-based storage engine (not the pure-Python 0.x). Multiple concurrent `PersistentClient` instances on the same path will corrupt Rust bindings → always use the `get_kb()` singleton.

## Key Constraints

- Ollama must be running before starting the API or pipeline.
- Pipeline must run at least once before the frontend can show data (reads JSON files).
- `CriticAgent` rejection exits the pipeline — frontend shows stale data from previous run.
- KB is optional (`use_kb=False` skips RAG) but improves effort estimate accuracy.
- `/api/ai/explain` returns 404 if pipeline hasn't run yet.
- `ai_explain.py` calls Ollama directly via `requests` (not `OllamaClient`) with shorter context to keep responses fast.
- `tasks_final.json` is only created after Admin Review submission; before that the canonical task list is `tasks.json`.
- Export endpoint (`GET /api/export/tasks`) prefers `tasks_final.json` after Admin Review, then falls back to `tasks.json`.
- `openpyxl` must be installed (`pip install openpyxl`) for the export endpoint to work.
- `tech_stack` in `tasks.json` is `null` for pipeline runs before this field was added; the frontend and `/api/data/tech-stack` endpoint handle `null` gracefully.
- `f1_fr` and `f1_nfr` in evaluation results return `-1.0` (not 0) for samples missing `task_classifications` in ground truth — this is intentional to distinguish "not measured" from "scored zero".
- The evaluation benchmark always forces rule-based mode via `FallbackOnlyClient`. Running `--ablation` is the only way to measure LLM contribution through the evaluation framework.
- **Never call `KnowledgeBase()` directly in API or pipeline code** — use `get_kb()` to avoid ChromaDB 1.x concurrent-client crashes. The pipeline helper `_load_knowledge_base_for_pipeline()` in `doc_to_tasks.py` wraps this with error recovery via `reset_kb()`.
- **Windows `PermissionError` on `api_input.txt`**: concurrent API requests can transiently lock the file. `_write_with_retry()` in `pipeline.py` retries up to 3 times with 0.3s delay — use it instead of `Path.write_text()` directly when writing pipeline input files on Windows.
