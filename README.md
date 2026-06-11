# CritiPlan - AI Project Manager

CritiPlan is a graduation-project platform that turns software requirements into project-management artifacts using a hybrid AI pipeline. It accepts a raw project brief or a structured requirements template, extracts requirements, generates tasks, estimates effort, builds dependencies, highlights risks, and presents the results in a dashboard for students and supervisors.

The project is designed to be local-first. When Ollama is available, the planner can use a local Qwen model. When it is not available, the system can still run through deterministic fallback logic, which makes the project easier to demo, test, and evaluate offline.

## What the system does

- Parse free-text briefs and structured requirement templates
- Generate validated task lists with FR/NFR traceability
- Estimate effort using rule-based logic plus knowledge-base context
- Build a dependency graph for execution order and planning
- Produce planning outputs such as summaries, risk reports, and review artifacts
- Provide a React dashboard for analytics, review, monitoring, and communication
- Expose the workflow through a FastAPI backend

## Main features

- Dashboard with planning overview and progress snapshots
- Plan view, Gantt timeline, dependency graph, and risk indicators
- Student and supervisor workspaces
- Committee brief and supervisor review flow
- Knowledge-base statistics and evaluation reports
- Repository monitoring and AI explanation endpoints

## Tech stack

- Backend: Python, FastAPI, Uvicorn, Pydantic
- Frontend: React, TypeScript, Vite, Zustand, Recharts
- AI layer: Ollama with local Qwen model
- Retrieval and storage: ChromaDB
- Graph analysis: NetworkX
- Optional dashboard: Streamlit

## Architecture summary

The system follows a multi-stage planning pipeline:

1. Input brief or template
2. Requirement parsing and normalization
3. Planning agent with optional Ollama/Qwen support
4. Validation and critique layer
5. Effort estimation and dependency graph construction
6. Risk analysis, summaries, exports, and evaluation

For more technical details, see [docs/architecture.md](docs/architecture.md).

## Repository structure

```text
src/
  agents/        Planner, critic, monitor, risk analysis
  api/           FastAPI app and routers
  core/          Shared schemas and runtime helpers
  graph/         Dependency graph logic
  kb/            Knowledge base and seeding
  llm/           Ollama client
  parsers/       Brief and template parsers
  pipelines/     End-to-end planning and evaluation workflows
  services/      Estimation, sprint planning, brief generation
  ui/            Streamlit UI

frontend/        React dashboard
data/            Sample briefs, processed outputs, evaluation artifacts
docs/            Architecture and supporting documentation
scripts/         Demo, verification, and helper scripts
tests/           Automated tests
```

## Quick start

### 1. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 3. Optional: seed the knowledge base

```bash
python -m src.kb.seed_cli
```

### 4. Optional: create the local Ollama model

The repository includes `models/Modelfile`, but the large `.gguf` model files are intentionally not committed.

```bash
ollama create ai-project-manager-planner -f models/Modelfile
```

If Ollama is not installed or not running, the project can still work in fallback mode for demos and testing.

## Run the project

### Option A: easiest Windows startup

```bat
START_FULL.BAT
```

This starts:

- FastAPI backend on `http://127.0.0.1:8000`
- React frontend on `http://127.0.0.1:5173/login`
- Optional Streamlit dashboard on `http://127.0.0.1:8501`

### Option B: presentation-safe startup

```bat
START_PRESENTATION_SAFE.BAT
```

This uses fast demo fallback settings and is useful when you want a stable local demo without relying heavily on the LLM.

### Option C: run services manually

Backend:

```bash
python run_api.py
```

Frontend:

```bash
cd frontend
npm run dev
```

Optional Streamlit UI:

```bash
python run_ui.py
```

## Demo login accounts

The frontend currently includes local demo credentials:

- Student
  - ID: `STU-2024`
  - Name: `Ahmed Khalid`
  - Password: `student123`
- Supervisor
  - Code: `SUPER-ADM`
  - Password: `supervisor123`

## Run the planning pipeline only

If you want to generate planning artifacts without opening the full UI:

```bash
python -m src.pipelines.run_all
```

Useful flags:

```bash
python -m src.pipelines.run_all --input data/raw/docs/project_brief_sample.txt
python -m src.pipelines.run_all --format template
python -m src.pipelines.run_all --skip-eval
python -m src.pipelines.run_all --force-fallback
```

## Generated outputs

After running the pipeline, the main outputs are:

- `data/processed/tasks.json`
- `data/processed/plan_summary.json`
- `data/processed/risk_report.json`
- `data/processed/tasks_final.json`
- `storage/graph/dependency_graph.json`
- `data/evaluation/evaluation_report.json`
- `data/evaluation/evaluation_report.md`

## Why this project matters

Early-stage software planning is often manual, inconsistent, and hard to justify academically. CritiPlan focuses on that gap by combining:

- requirement parsing
- AI-assisted decomposition
- rule-based validation
- effort estimation
- dependency analysis
- reproducible evaluation

The result is a system that is not only able to generate project artifacts, but also explain and evaluate how those artifacts were produced.

## Notes

- The large local model files are not included in this repository.
- Some saved outputs in `data/processed/` and `data/evaluation/` are included as example artifacts.
- The project supports both local-AI mode and fallback mode.

## License

This repository currently does not include a license file. Add one before public reuse if needed.
