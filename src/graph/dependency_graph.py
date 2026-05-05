from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import networkx as nx

from src.core.schemas import TaskList


class DependencyGraph:
    """NetworkX DAG built from a TaskList for project scheduling analytics.

    Edge direction: dependency -> task
    (an edge A->B means "A must finish before B can start")

    Edge weight: complexity of the destination task (cost of unlocking it).
    This lets dag_longest_path find the path that accumulates the most effort —
    the true critical path a team must optimize.
    """

    def __init__(self, task_list: TaskList) -> None:
        self._tasks = {task.id: task for task in task_list.tasks}
        self._graph: nx.DiGraph = nx.DiGraph()
        self._build(task_list)

    def _build(self, task_list: TaskList) -> None:
        for task in task_list.tasks:
            self._graph.add_node(
                task.id,
                title=task.title,
                req_type=task.req_type,
                complexity=task.complexity,
                source=task.source,
                optional=task.optional,
                confidence=task.confidence,
                estimated_hours=task.estimated_hours,
                recommended_team_size=task.recommended_team_size,
                skill_required=task.skill_required,
                suggested_owner_role=task.suggested_owner_role,
                risks=task.risks,
            )
        for task in task_list.tasks:
            for dep_id in task.dependencies:
                self._graph.add_edge(dep_id, task.id, weight=task.complexity)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Return cycle descriptions. Empty list = valid DAG."""
        issues: list[str] = []
        try:
            for cycle in nx.simple_cycles(self._graph):
                issues.append(" -> ".join(cycle + [cycle[0]]))
        except nx.NetworkXError as exc:
            issues.append(f"Graph structure error: {exc}")
        return issues

    # ------------------------------------------------------------------
    # Critical path
    # ------------------------------------------------------------------

    def critical_path(self) -> list[str]:
        """Ordered task IDs on the longest complexity-weighted path."""
        if not self._graph.nodes:
            return []
        return nx.dag_longest_path(self._graph, weight="weight")

    def critical_path_length(self) -> int:
        """Sum of complexity weights along the critical path."""
        if not self._graph.nodes:
            return 0
        return int(nx.dag_longest_path_length(self._graph, weight="weight"))

    # ------------------------------------------------------------------
    # Structural analytics
    # ------------------------------------------------------------------

    def bottleneck_tasks(self, top_n: int = 5) -> list[dict[str, Any]]:
        """Tasks ranked by out-degree (most downstream dependents).

        A high out-degree means many other tasks are blocked until this one
        is done — these are the tasks the team must prioritize first.
        """
        scored = [
            {
                "id": node,
                "title": self._tasks[node].title,
                "blocks": self._graph.out_degree(node),
                "complexity": self._tasks[node].complexity,
            }
            for node in self._graph.nodes
        ]
        scored.sort(key=lambda x: (-x["blocks"], -x["complexity"]))
        return scored[:top_n]

    def root_tasks(self) -> list[str]:
        """Task IDs with no incoming edges — project entry points."""
        return [n for n in self._graph.nodes if self._graph.in_degree(n) == 0]

    def leaf_tasks(self) -> list[str]:
        """Task IDs with no outgoing edges — final deliverables."""
        return [n for n in self._graph.nodes if self._graph.out_degree(n) == 0]

    def parallel_groups(self) -> list[list[str]]:
        """Topological generations: tasks in the same group can run in parallel.

        Each group's tasks have all dependencies satisfied by earlier groups.
        The number of groups is the minimum number of sequential phases needed.
        """
        return [sorted(group) for group in nx.topological_generations(self._graph)]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Full analytics dict — written into plan_summary.json."""
        cp_ids = self.critical_path()
        cp_titles = [self._tasks[tid].title for tid in cp_ids if tid in self._tasks]
        bottlenecks = self.bottleneck_tasks(top_n=5)
        groups = self.parallel_groups()
        cycle_issues = self.validate()

        total = len(self._tasks)
        fr_count = sum(1 for t in self._tasks.values() if t.req_type == "FR")
        nfr_count = total - fr_count
        avg_complexity = round(
            sum(t.complexity for t in self._tasks.values()) / total, 2
        ) if total else 0.0

        complexity_dist = {str(c): 0 for c in range(1, 6)}
        for t in self._tasks.values():
            complexity_dist[str(t.complexity)] += 1

        low_confidence_tasks = [
            {
                "id": task.id,
                "title": task.title,
                "source": task.source,
                "confidence": task.confidence,
                "optional": task.optional,
            }
            for task in self._tasks.values()
            if task.optional or task.confidence == "low"
        ]

        suspicious_isolated_tasks: list[dict[str, Any]] = []
        validation_warnings: list[str] = []
        if total > 1:
            from src.agents.planner import PlannerAgent

            def is_valid_public_read_root(description: str, tags: set[str]) -> bool:
                if "view" not in tags:
                    return False
                if tags & {"export", "reporting", "dashboard", "evaluation", "validation"}:
                    return False
                if re.search(
                    r"\b(browse|search|filter|view|read|list|display|show)\b",
                    description,
                    flags=re.IGNORECASE,
                ) is None:
                    return False
                return re.search(
                    r"\b(public|help center|documentation|docs?|knowledge base|faq|catalog|catalogue|pricing|plans?)\b",
                    description,
                    flags=re.IGNORECASE,
                ) is not None

            for task_id, task in self._tasks.items():
                if self._graph.in_degree(task_id) != 0 or self._graph.out_degree(task_id) != 0:
                    continue
                tags = PlannerAgent._extract_semantic_tags(task.description)
                suspicious = bool(
                    {"export", "reporting", "view", "dashboard", "evaluation", "validation"} & tags
                    or re.search(
                        r"\b(export|download|critic|feedback|validation|clarification|ambiguous|assumptions?)\b",
                        task.description,
                        flags=re.IGNORECASE,
                    )
                )
                root_by_design = bool(
                    {"foundation", "identity", "requirements_ingestion", "offline_operation"} & tags
                )
                public_read_root = is_valid_public_read_root(task.description, tags)
                if suspicious and not root_by_design and not public_read_root:
                    suspicious_isolated_tasks.append(
                        {
                            "id": task.id,
                            "title": task.title,
                            "source": task.source,
                            "tags": sorted(tags),
                        }
                    )
                    validation_warnings.append(
                        f"Task {task.id} ({task.title}) is isolated despite depending on upstream workflow artifacts."
                    )

            for task_id, task in self._tasks.items():
                tags = PlannerAgent._extract_semantic_tags(task.description)
                is_performance_nfr = task.req_type == "NFR" and (
                    "performance" in tags
                    or re.search(
                        r"\b(performance|scalab|latency|throughput|response time|concurrent)\b",
                        task.description,
                        flags=re.IGNORECASE,
                    ) is not None
                )
                if not is_performance_nfr:
                    continue

                for dep_id in task.dependencies:
                    dep_task = self._tasks.get(dep_id)
                    if dep_task is None or dep_task.req_type != "FR":
                        continue
                    dep_tags = PlannerAgent._extract_semantic_tags(dep_task.description)
                    downstream_surface = bool(
                        dep_tags & {"dashboard", "reporting", "export", "integration", "evaluation"}
                    ) or (
                        "view" in dep_tags
                        and re.search(r"\b(view|display|show|read|access|surface)\b", dep_task.description, flags=re.IGNORECASE)
                    ) or (
                        re.search(
                            r"\b(dashboard|reports?|analytics|metrics|summary|summaries|export|download|api|ui|user interface|view|display|show)\b",
                            dep_task.description,
                            flags=re.IGNORECASE,
                        )
                        is not None
                    )
                    if downstream_surface:
                        validation_warnings.append(
                            f"Performance/scalability task {task.id} ({task.title}) depends on downstream functional surface {dep_task.id} ({dep_task.title}); dependency direction should be reversed."
                        )

        return {
            "total_tasks": total,
            "total_dependencies": self._graph.number_of_edges(),
            "fr_count": fr_count,
            "nfr_count": nfr_count,
            "avg_complexity": avg_complexity,
            "complexity_distribution": complexity_dist,
            "optional_task_count": len(low_confidence_tasks),
            "confirmed_task_count": total - len(low_confidence_tasks),
            "low_confidence_tasks": low_confidence_tasks,
            "is_valid_dag": len(cycle_issues) == 0,
            "cycle_issues": cycle_issues,
            "critical_path": {
                "task_ids": cp_ids,
                "titles": cp_titles,
                "total_weight": self.critical_path_length(),
                "length": len(cp_ids),
            },
            "bottleneck_tasks": bottlenecks,
            "root_tasks": self.root_tasks(),
            "leaf_tasks": self.leaf_tasks(),
            "suspicious_isolated_tasks": suspicious_isolated_tasks,
            "validation_warnings": validation_warnings,
            "parallel_groups": groups,
            "parallel_group_count": len(groups),
        }

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Write node-link JSON — compatible with D3.js and Cytoscape.js."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._graph)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
