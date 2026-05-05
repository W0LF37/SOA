from __future__ import annotations

from src.kb.vector_store import KnowledgeBase


class ContextRetriever:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def get_context_for_requirement(self, req_text: str) -> str:
        results = self.kb.query(req_text, n_results=5)
        examples = [r for r in results if r.get("category") == "planning_example"]
        if not examples:
            return ""

        lines = [
            "## Retrieved KB Context for LLM Planning",
            "Use these similar projects as calibration signals for task scope, "
            "FR/NFR classification, complexity levels, and dependency hints. "
            "Do not copy tasks unless they are implied by the new requirements.",
            "Hard constraints for this run: emit one task per requirement line, do not merge repeated source lines, "
            "keep security/performance/compliance/availability/mobile/localization/privacy constraints as NFRs, "
            "and keep titles action-oriented (Implement/Integrate for FR; Enforce/Optimize/Enable for NFR).",
        ]
        for r in examples[:2]:
            meta = r.get("metadata", {})
            domain = meta.get("domain", "unknown")
            score = meta.get("critic_score", "")
            task_examples = meta.get("example_tasks", "")
            score_str = f", critic_score={score}" if score else ""
            lines.append(f"\n### {domain.upper()} project{score_str}:")
            for task_line in task_examples.split("|"):
                task_line = task_line.strip()
                if task_line:
                    lines.append(f"  - {task_line}")

        lines.append(
            "\nApply similar FR/NFR classification and complexity levels "
            "to the new requirements below, while preserving exact source references and the one-line-to-one-task mapping."
        )
        return "\n".join(lines)
