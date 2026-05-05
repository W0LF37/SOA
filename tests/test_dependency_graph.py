from __future__ import annotations

import unittest
from pathlib import Path

from src.agents.planner import PlannerAgent
from src.core.schemas import Task, TaskList
from src.graph.dependency_graph import DependencyGraph
from tests.test_planner_agent import HEALTHCARE_REQUIREMENTS


def _make_task_list(*specs: tuple[str, list[str], int]) -> TaskList:
    """Helper: specs = (id, dependencies, complexity)."""
    tasks = [
        Task(
            id=tid,
            title=f"Implement {tid} workflow",
            description=f"Task {tid}.",
            req_type="FR",
            complexity=complexity,
            dependencies=deps,
            source="line 1",
        )
        for tid, deps, complexity in specs
    ]
    return TaskList(tasks=tasks)


class DependencyGraphValidationTests(unittest.TestCase):
    def test_valid_dag_has_no_cycles(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 2),
            ("T002", ["T001"], 3),
            ("T003", ["T001"], 2),
            ("T004", ["T002", "T003"], 4),
        )
        graph = DependencyGraph(task_list)
        self.assertEqual(graph.validate(), [])

    def test_single_task_is_valid(self) -> None:
        task_list = _make_task_list(("T001", [], 3))
        graph = DependencyGraph(task_list)
        self.assertEqual(graph.validate(), [])

    def test_linear_chain_is_valid(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 1),
            ("T002", ["T001"], 2),
            ("T003", ["T002"], 3),
        )
        graph = DependencyGraph(task_list)
        self.assertEqual(graph.validate(), [])


class DependencyGraphCriticalPathTests(unittest.TestCase):
    def test_critical_path_follows_highest_weight(self) -> None:
        # T001(2) -> T002(5) -> T004(1)  weight=8
        # T001(2) -> T003(1) -> T004(1)  weight=4
        # Critical path must be T001->T002->T004
        task_list = _make_task_list(
            ("T001", [], 2),
            ("T002", ["T001"], 5),
            ("T003", ["T001"], 1),
            ("T004", ["T002", "T003"], 1),
        )
        graph = DependencyGraph(task_list)
        cp = graph.critical_path()
        self.assertIn("T001", cp)
        self.assertIn("T002", cp)
        self.assertIn("T004", cp)

    def test_critical_path_length_correct(self) -> None:
        # Linear: T001(3) -> T002(4) -> T003(2)  total weight = 4+2 = 6
        task_list = _make_task_list(
            ("T001", [], 3),
            ("T002", ["T001"], 4),
            ("T003", ["T002"], 2),
        )
        graph = DependencyGraph(task_list)
        self.assertEqual(graph.critical_path_length(), 6)

    def test_single_task_critical_path(self) -> None:
        task_list = _make_task_list(("T001", [], 3))
        graph = DependencyGraph(task_list)
        self.assertEqual(graph.critical_path(), ["T001"])
        self.assertEqual(graph.critical_path_length(), 0)


class DependencyGraphStructureTests(unittest.TestCase):
    def test_root_tasks_have_no_dependencies(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 1),
            ("T002", [], 1),
            ("T003", ["T001"], 2),
            ("T004", ["T002"], 2),
        )
        graph = DependencyGraph(task_list)
        self.assertCountEqual(graph.root_tasks(), ["T001", "T002"])

    def test_leaf_tasks_have_no_dependents(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 1),
            ("T002", ["T001"], 2),
            ("T003", ["T001"], 2),
        )
        graph = DependencyGraph(task_list)
        self.assertCountEqual(graph.leaf_tasks(), ["T002", "T003"])

    def test_bottleneck_task_is_highest_outdegree(self) -> None:
        # T001 blocks T002, T003, T004 (out-degree=3)
        task_list = _make_task_list(
            ("T001", [], 2),
            ("T002", ["T001"], 1),
            ("T003", ["T001"], 1),
            ("T004", ["T001"], 1),
        )
        graph = DependencyGraph(task_list)
        bottlenecks = graph.bottleneck_tasks(top_n=1)
        self.assertEqual(bottlenecks[0]["id"], "T001")
        self.assertEqual(bottlenecks[0]["blocks"], 3)

    def test_parallel_groups_correct_count(self) -> None:
        # Stage 1: T001
        # Stage 2: T002, T003 (both depend on T001, independent of each other)
        # Stage 3: T004 (depends on T002 and T003)
        task_list = _make_task_list(
            ("T001", [], 1),
            ("T002", ["T001"], 1),
            ("T003", ["T001"], 1),
            ("T004", ["T002", "T003"], 1),
        )
        graph = DependencyGraph(task_list)
        groups = graph.parallel_groups()
        self.assertEqual(len(groups), 3)
        self.assertIn("T001", groups[0])
        self.assertIn("T002", groups[1])
        self.assertIn("T003", groups[1])
        self.assertIn("T004", groups[2])

    def test_independent_tasks_in_same_parallel_group(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 1),
            ("T002", [], 1),
            ("T003", [], 1),
        )
        graph = DependencyGraph(task_list)
        groups = graph.parallel_groups()
        self.assertEqual(len(groups), 1)
        self.assertCountEqual(groups[0], ["T001", "T002", "T003"])


class DependencyGraphSummaryTests(unittest.TestCase):
    def test_summary_counts_correct(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 2),
            ("T002", ["T001"], 3),
            ("T003", ["T001"], 4),
        )
        graph = DependencyGraph(task_list)
        summary = graph.summary()

        self.assertEqual(summary["total_tasks"], 3)
        self.assertEqual(summary["total_dependencies"], 2)
        self.assertTrue(summary["is_valid_dag"])
        self.assertEqual(summary["cycle_issues"], [])
        self.assertEqual(summary["root_tasks"], ["T001"])
        self.assertCountEqual(summary["leaf_tasks"], ["T002", "T003"])

    def test_summary_avg_complexity(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 2),
            ("T002", [], 4),
        )
        graph = DependencyGraph(task_list)
        self.assertEqual(graph.summary()["avg_complexity"], 3.0)

    def test_summary_complexity_distribution(self) -> None:
        task_list = _make_task_list(
            ("T001", [], 1),
            ("T002", [], 2),
            ("T003", [], 2),
            ("T004", [], 4),
        )
        graph = DependencyGraph(task_list)
        dist = graph.summary()["complexity_distribution"]
        self.assertEqual(dist["1"], 1)
        self.assertEqual(dist["2"], 2)
        self.assertEqual(dist["3"], 0)
        self.assertEqual(dist["4"], 1)
        self.assertEqual(dist["5"], 0)

    def test_summary_flags_suspicious_isolated_non_root_task(self) -> None:
        task_list = TaskList(tasks=[
            Task(
                id="T001",
                title="Implement requirements ingestion workflow",
                description="The system must accept project requirements in multiple formats.",
                req_type="FR",
                complexity=2,
                dependencies=[],
                source="line 1",
            ),
            Task(
                id="T002",
                title="Implement task and report export workflow",
                description="The system must allow exporting generated tasks and reports in multiple formats.",
                req_type="FR",
                complexity=2,
                dependencies=[],
                source="line 2",
            ),
        ])
        graph = DependencyGraph(task_list)
        summary = graph.summary()
        self.assertEqual([item["id"] for item in summary["suspicious_isolated_tasks"]], ["T002"])
        self.assertEqual(len(summary["validation_warnings"]), 1)

    def test_summary_does_not_flag_valid_root_with_dependents(self) -> None:
        task_list = TaskList(tasks=[
            Task(
                id="T001",
                title="Implement requirements ingestion workflow",
                description="The system must accept project requirements in multiple formats.",
                req_type="FR",
                complexity=2,
                dependencies=[],
                source="line 1",
            ),
            Task(
                id="T002",
                title="Implement structured task generation workflow",
                description="The system must automatically generate a structured list of tasks.",
                req_type="FR",
                complexity=2,
                dependencies=["T001"],
                source="line 2",
            ),
        ])
        graph = DependencyGraph(task_list)
        summary = graph.summary()
        self.assertIn("T001", summary["root_tasks"])
        self.assertEqual(summary["suspicious_isolated_tasks"], [])

    def test_summary_does_not_flag_valid_public_read_only_root(self) -> None:
        task_list = TaskList(tasks=[
            Task(
                id="T001",
                title="Implement public help center browsing workflow",
                description="Users can browse the public help center documentation.",
                req_type="FR",
                complexity=1,
                dependencies=[],
                source="line 1",
            ),
            Task(
                id="T002",
                title="Implement patient billing workflow",
                description="Staff can update billing entries.",
                req_type="FR",
                complexity=2,
                dependencies=[],
                source="line 2",
            ),
        ])
        graph = DependencyGraph(task_list)
        summary = graph.summary()
        self.assertIn("T001", summary["root_tasks"])
        self.assertNotIn("T001", [item["id"] for item in summary["suspicious_isolated_tasks"]])

    def test_summary_flags_inverted_performance_dependency(self) -> None:
        task_list = TaskList(tasks=[
            Task(
                id="T001",
                title="Implement project planning dashboard",
                description="The system must provide a user interface dashboard displaying task breakdown and risk indicators.",
                req_type="FR",
                complexity=3,
                dependencies=[],
                source="line 1",
            ),
            Task(
                id="T002",
                title="Optimize planner scalability for large project portfolios",
                description="The system must support scalability to handle projects with at least 200 tasks without significant performance degradation.",
                req_type="NFR",
                complexity=4,
                dependencies=["T001"],
                source="line 2",
            ),
        ])
        graph = DependencyGraph(task_list)
        summary = graph.summary()
        self.assertTrue(
            any("Performance/scalability task T002" in warning for warning in summary["validation_warnings"]),
            summary["validation_warnings"],
        )

    def test_summary_surfaces_optional_scope_metadata(self) -> None:
        task_list = TaskList(tasks=[
            Task(
                id="T001",
                title="Implement ambulance tracking support workflow",
                description="The system must support ambulance tracking, maybe in a later phase.",
                req_type="FR",
                complexity=2,
                dependencies=[],
                source="line 1",
                optional=True,
                confidence="low",
            ),
            Task(
                id="T002",
                title="Implement appointment booking workflow",
                description="Patients can book appointments online.",
                req_type="FR",
                complexity=2,
                dependencies=[],
                source="line 2",
                optional=False,
                confidence="high",
            ),
        ])
        graph = DependencyGraph(task_list)
        summary = graph.summary()
        self.assertEqual(summary["optional_task_count"], 1)
        self.assertEqual(summary["confirmed_task_count"], 1)
        self.assertEqual(summary["low_confidence_tasks"][0]["id"], "T001")
        self.assertEqual(summary["low_confidence_tasks"][0]["confidence"], "low")


class DependencyGraphIntegrationTests(unittest.TestCase):
    """End-to-end: build graph from the real healthcare plan."""

    @classmethod
    def setUpClass(cls) -> None:
        planner = PlannerAgent(llm_client=_FakeLLMClient({}))
        task_list = planner.plan_from_requirements(
            HEALTHCARE_REQUIREMENTS,
            allow_fallback=True,
            allow_decomposition=True,
        )
        cls.graph = DependencyGraph(task_list)
        cls.summary = cls.graph.summary()

    def test_no_cycles_in_healthcare_plan(self) -> None:
        self.assertTrue(self.summary["is_valid_dag"])
        self.assertEqual(self.summary["cycle_issues"], [])

    def test_has_critical_path(self) -> None:
        cp = self.summary["critical_path"]
        self.assertGreater(cp["length"], 0)
        self.assertGreater(cp["total_weight"], 0)

    def test_identity_or_access_foundation_is_top_bottleneck(self) -> None:
        bottlenecks = self.summary["bottleneck_tasks"]
        top_bottleneck = bottlenecks[0]
        self.assertTrue(
            any(
                phrase in top_bottleneck["title"].lower()
                for phrase in ("role-based access control", "account verification", "registration")
            ),
            f"Unexpected top bottleneck: {top_bottleneck}",
        )
        rbac_bottleneck = next(
            (
                item for item in bottlenecks
                if "role-based access control" in item["title"].lower()
            ),
            None,
        )
        self.assertIsNotNone(rbac_bottleneck, "RBAC should remain a major bottleneck")
        self.assertGreater(rbac_bottleneck["blocks"], 5)

    def test_parallel_groups_exist(self) -> None:
        self.assertGreater(self.summary["parallel_group_count"], 1)

    def test_at_least_one_root_task(self) -> None:
        self.assertGreater(len(self.summary["root_tasks"]), 0)

    def test_save_produces_valid_json(self, tmp_path: Path | None = None) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "graph.json"
            self.graph.save(out)
            self.assertTrue(out.exists())
            data = json.loads(out.read_text())
            self.assertIn("nodes", data)


class _FakeLLMClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def generate_json(self, prompt: str, output_schema=None, strict_json_only: bool = False):  # noqa: ANN001
        return self.payload


if __name__ == "__main__":
    unittest.main()
