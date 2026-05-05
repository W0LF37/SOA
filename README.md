## Quick Start

1. Put your Project Brief at:
   data/raw/docs/project_brief_sample.txt

2. (First time only) Create the local Ollama model from the bundled GGUF:
   ollama create ai-project-manager-planner -f models/Modelfile

3. Run the full pipeline (planning + evaluation) with one command:
   python -m src.pipelines.run_all

   This will:
   - Parse the Project Brief
   - Generate tasks.json, plan_summary.json, dependency_graph.json
   - Run planner quality evaluation against ground_truth.json
   - Print a combined report to the terminal
   - Write evaluation_report.md and evaluation_report.json

4. Output files:
   data/processed/tasks.json            — task list
   data/processed/plan_summary.json     — full analytics + sprint plan
   storage/graph/dependency_graph.json  — dependency graph
   data/evaluation/evaluation_report.md — human-readable evaluation report
   data/evaluation/evaluation_report.json — machine-readable evaluation

5. Optional flags:
   --input PATH         Use a different brief file
   --format template    Use structured REQ-NN template format instead
   --skip-eval          Skip evaluation phase
   --no-force-fallback  Use the Ollama LLM instead of rule-based planner

## Academic Contribution

This project addresses the early-stage software planning gap between informal requirements and executable project management artifacts. Traditional estimation methods such as COCOMO and Function Points help size work, but they do not automatically produce validated task lists, dependency graphs, sprint plans, risk reports, and reproducible evaluation metrics from raw requirement documents.

The system is a hybrid LLM-guided agentic planning pipeline. Ollama/Qwen acts as the local Planning Reasoner, ChromaDB supplies a retrieval-augmented knowledge base of curated planning examples and estimation patterns, and rule-based validators provide deterministic safety checks when LLM output is invalid or unavailable. NetworkX then converts accepted tasks into dependency-aware delivery structures.

This is intentionally not a custom-trained ML estimator. The project uses RAG and structured evaluation instead: the LLM reasons over retrieved examples, the EffortEstimator calibrates hours against task-level knowledge-base records, and the pipeline records whether the LLM was attempted, accepted, or replaced by fallback rules.

The latest saved evaluation artifacts cover 19 benchmark samples and include an ablation study comparing `Rules only`, `Rules + KB`, `LLM + KB`, and `Zero-shot LLM`. The saved ablation report shows the KB improving estimation MMRE from 0.751 to 0.653 while preserving a 100.0% pass rate.

To reproduce the results:

1. Create the local planner model:
   `ollama create ai-project-manager-planner -f models/Modelfile`

2. Seed the Knowledge Base:
   `python -m src.kb.seed_cli`

3. Run the full pipeline and evaluation:
   `python -m src.pipelines.run_all`

4. Review the generated reports:
   `data/evaluation/evaluation_report.json`, `data/evaluation/evaluation_report.md`, and `data/evaluation/ablation_report.json`

5. Run the fast ablation comparison for day-to-day validation:
   `python -m src.pipelines.evaluate --ablation-fast`

6. Run the full ablation comparison, including slow LLM and zero-shot conditions:
   `python -m src.pipelines.evaluate --ablation`
