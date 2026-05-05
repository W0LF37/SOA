from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, Literal

import numpy as np

from src.core.schemas import CommitInfo, MonitorReport, TaskList, TaskProgress

if TYPE_CHECKING:
    from src.llm.ollama_client import OllamaClient


class SemanticMatcher:
    """Semantic commit-to-task matcher using sentence-transformers."""

    SIMILARITY_THRESHOLD = 0.65

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self._task_embeddings: dict[str, list[float]] = {}

    def precompute(self, task_list: TaskList) -> None:
        texts = [f"{t.title}. {t.description}" for t in task_list.tasks]
        embeddings = self.model.encode(texts, show_progress_bar=False)
        self._task_embeddings = {
            t.id: embeddings[i].tolist()
            for i, t in enumerate(task_list.tasks)
        }

    def similarity(self, commit_text: str, task_id: str) -> float:
        if task_id not in self._task_embeddings:
            return 0.0
        commit_emb = self.model.encode([commit_text], show_progress_bar=False)[0]
        task_emb   = np.array(self._task_embeddings[task_id])
        commit_emb = np.array(commit_emb)
        denom = np.linalg.norm(commit_emb) * np.linalg.norm(task_emb)
        if denom < 1e-8:
            return 0.0
        return float(np.dot(commit_emb, task_emb) / denom)

    def matches(self, commit_text: str, task_id: str) -> bool:
        return self.similarity(commit_text, task_id) >= self.SIMILARITY_THRESHOLD


class MonitorAgent:
    """
    Phase 5 — Git-based progress tracker.

    Reads commits from a Git repository, maps them to tasks via keyword
    matching, and produces a MonitorReport with per-task and overall progress.

    Usage::

        agent = MonitorAgent()

        # With real git repo:
        report = agent.track_progress(task_list, repo_path="/path/to/repo")

        # For testing (pass commits directly):
        report = agent.track_progress(task_list, commits=[...])
    """

    _STOP_WORDS: frozenset[str] = frozenset({
        "a", "an", "the", "and", "or", "in", "for", "of", "to", "with",
        "is", "are", "be", "by", "on", "at", "from", "into", "as", "its",
        "this", "that", "it", "not", "no", "task",
    })
    _DONE_KEYWORDS: frozenset[str] = frozenset({
        "done", "complete", "completed", "finish", "finished",
        "close", "closed", "fix", "fixed",
        "merge", "merged", "resolve", "resolved",
    })

    def __init__(
        self,
        llm_client: "OllamaClient | None" = None,
        use_semantic: bool = True,
    ) -> None:
        self._llm = llm_client
        self._matcher: SemanticMatcher | None = None
        if use_semantic:
            try:
                self._matcher = SemanticMatcher()
            except Exception:  # noqa: BLE001
                self._matcher = None   # graceful fallback to keyword matching

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def track_progress(
        self,
        task_list: TaskList,
        repo_path: str | None = None,
        commits: list[dict] | None = None,
    ) -> MonitorReport:
        """Map git commits to tasks and return a MonitorReport."""
        if commits is not None:
            commit_objs = [CommitInfo(**c) for c in commits]
        elif repo_path is not None:
            commit_objs = self._read_git_commits(repo_path)
        else:
            commit_objs = []

        if self._matcher is not None and commit_objs:
            self._matcher.precompute(task_list)
        task_progress = self._map_commits_to_tasks(task_list, commit_objs)
        overall = self._compute_overall_progress(task_progress, task_list)
        behind = self._detect_behind_schedule(task_progress, task_list)

        completed = sum(1 for tp in task_progress if tp.status == "completed")
        in_progress = sum(1 for tp in task_progress if tp.status == "in_progress")
        not_started = sum(1 for tp in task_progress if tp.status == "not_started")

        return MonitorReport(
            overall_progress=round(overall, 3),
            tasks_tracked=len(task_progress),
            tasks_completed=completed,
            tasks_in_progress=in_progress,
            tasks_not_started=not_started,
            task_progress=task_progress,
            commits_analyzed=len(commit_objs),
            behind_schedule=behind,
        )

    # ------------------------------------------------------------------ #
    # Git Reading                                                          #
    # ------------------------------------------------------------------ #

    def _read_git_commits(self, repo_path: str) -> list[CommitInfo]:
        """Read last 200 commits from git repo using subprocess."""
        try:
            result = subprocess.run(
                ["git", "log", "--format=%H|||%s|||%ae|||%ci", "-n", "200"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return []

            commits: list[CommitInfo] = []
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|||")
                if len(parts) < 4:
                    continue
                sha, message, author, date = (
                    parts[0], parts[1], parts[2], parts[3].strip()
                )
                commits.append(
                    CommitInfo(sha=sha, message=message, author=author, date=date)
                )

            self._enrich_with_files(commits, repo_path)
            return commits
        except Exception:  # noqa: BLE001
            return []

    def _enrich_with_files(
        self, commits: list[CommitInfo], repo_path: str
    ) -> None:
        """Add files_changed to each commit (best-effort)."""
        try:
            result = subprocess.run(
                ["git", "log", "--name-only", "--format=%H", "-n", "200"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return

            sha_to_files: dict[str, list[str]] = {}
            current_sha: str | None = None
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                    current_sha = line
                    sha_to_files[current_sha] = []
                elif current_sha:
                    sha_to_files[current_sha].append(line)

            for commit in commits:
                commit.files_changed = sha_to_files.get(commit.sha, [])
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Task Mapping                                                         #
    # ------------------------------------------------------------------ #

    def _extract_keywords(self, title: str) -> frozenset[str]:
        """Extract meaningful keywords from a task title."""
        words = title.lower().replace("-", " ").replace("_", " ").split()
        return frozenset(w for w in words if w not in self._STOP_WORDS and len(w) > 2)

    def _commit_matches_task(
        self, commit: CommitInfo, keywords: frozenset[str]
    ) -> bool:
        """Check if a commit message or files reference any task keyword."""
        text = (commit.message + " " + " ".join(commit.files_changed)).lower()
        return any(
            re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text)
            for kw in keywords
        )

    def _is_noise_commit(self, commit: CommitInfo) -> bool:
        """Short/generic commit messages carry no signal for semantic matching."""
        title = commit.message.split("\n")[0].strip()
        return len(title) < 10

    def _map_commits_to_tasks(
        self, task_list: TaskList, commits: list[CommitInfo]
    ) -> list[TaskProgress]:
        from datetime import datetime, timezone

        semantic_best: dict[str, str] = {}
        if self._matcher is not None:
            for commit in commits:
                if self._is_noise_commit(commit):
                    continue
                commit_text = commit.message + " " + " ".join(commit.files_changed)
                scores = [
                    (self._matcher.similarity(commit_text, task.id), task.id)
                    for task in task_list.tasks
                ]
                if not scores:
                    continue
                score, task_id = max(scores, key=lambda item: item[0])
                if score >= self._matcher.SIMILARITY_THRESHOLD:
                    semantic_best[commit.sha] = task_id

        now = datetime.now(tz=timezone.utc)

        results: list[TaskProgress] = []
        for task in task_list.tasks:
            matched: list[CommitInfo] = []
            for commit in commits:
                # Semantic matching (preferred, skip noise commits)
                if self._matcher is not None and not self._is_noise_commit(commit):
                    if semantic_best.get(commit.sha) == task.id:
                        matched.append(commit)
                        continue

                # Keyword fallback
                keywords = self._extract_keywords(task.title)
                if self._commit_matches_task(commit, keywords):
                    matched.append(commit)

            n = len(matched)
            status: Literal["not_started", "in_progress", "completed"]
            if n == 0:
                status = "not_started"
                estimate = 0.0
            elif n >= 3:
                # High commit volume → completed regardless of keywords
                status = "completed"
                estimate = 1.0
            else:
                # Check if any matched commit has done-keywords
                all_words = set()
                for c in matched:
                    all_words.update(c.message.lower().split())
                has_done = bool(all_words & self._DONE_KEYWORDS)

                if n == 1 and not has_done:
                    # Check recency: recent → in_progress, stale → still in_progress
                    try:
                        commit_dt = datetime.fromisoformat(
                            matched[0].date.replace("Z", "+00:00")
                        )
                        age_days = (now - commit_dt).days
                    except Exception:  # noqa: BLE001
                        age_days = 0
                    status = "in_progress"
                    estimate = 0.5
                elif has_done:
                    status = "completed"
                    estimate = 1.0
                else:
                    # Two focused commits are treated as complete even without a done keyword.
                    status = "completed"
                    estimate = 1.0

            results.append(
                TaskProgress(
                    task_id=task.id,
                    task_title=task.title,
                    status=status,
                    matched_commits=[c.sha for c in matched],
                    evidence=[c.message for c in matched],
                    completion_estimate=estimate,
                )
            )
        return results

    # ------------------------------------------------------------------ #
    # Progress & Schedule                                                  #
    # ------------------------------------------------------------------ #

    def _compute_overall_progress(
        self, task_progress: list[TaskProgress], task_list: TaskList
    ) -> float:
        """Weighted average of completion_estimate by task complexity."""
        id_to_complexity = {t.id: t.complexity for t in task_list.tasks}
        total_weight = sum(
            id_to_complexity.get(tp.task_id, 1) for tp in task_progress
        )
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(
            tp.completion_estimate * id_to_complexity.get(tp.task_id, 1)
            for tp in task_progress
        )
        return weighted_sum / total_weight

    def _detect_behind_schedule(
        self, task_progress: list[TaskProgress], task_list: TaskList
    ) -> list[str]:
        """
        Detect tasks that are behind schedule:
        - not_started tasks that are dependencies of in_progress/completed tasks
        - complexity=5 tasks with 0 commits
        """
        id_to_task = {t.id: t for t in task_list.tasks}
        active_tasks = {
            tp.task_id
            for tp in task_progress
            if tp.status in {"in_progress", "completed"}
        }

        behind: list[str] = []
        for tp in task_progress:
            if tp.task_id in behind:
                continue
            task = id_to_task.get(tp.task_id)
            if task is None:
                continue

            # Rule 1: not_started but a dependee is already active
            if tp.status == "not_started":
                dependees = [
                    t.id for t in task_list.tasks if tp.task_id in t.dependencies
                ]
                if any(d in active_tasks for d in dependees):
                    behind.append(tp.task_id)
                    continue

            # Rule 2: complexity=5 with 0 commits
            if task.complexity == 5 and len(tp.matched_commits) == 0:
                behind.append(tp.task_id)

        return behind


def format_monitor_report(report: MonitorReport) -> str:
    """Return a human-readable summary of a MonitorReport."""
    SEP = "=" * 62
    DIV = "-" * 62
    pct = f"{report.overall_progress:.0%}"
    bar_filled = int(report.overall_progress * 20)
    bar = "[" + "#" * bar_filled + "-" * (20 - bar_filled) + "]"

    lines = [
        SEP,
        "  MONITOR AGENT  --  PHASE 5 PROGRESS REPORT",
        SEP,
        f"  Progress : {bar} {pct}",
        f"  Commits  : {report.commits_analyzed} analyzed",
        f"  Tasks    : {report.tasks_tracked} total  "
        f"({report.tasks_completed} done, "
        f"{report.tasks_in_progress} in progress, "
        f"{report.tasks_not_started} not started)",
    ]

    if report.behind_schedule:
        lines.append(
            f"\n  [WARN] Behind schedule: {', '.join(report.behind_schedule)}"
        )

    if report.task_progress:
        lines.append("\n  TASK BREAKDOWN")
        lines.append(f"  {DIV}")
        icons = {
            "completed": "[DONE]",
            "in_progress": "[WIP] ",
            "not_started": "[    ]",
        }
        for tp in report.task_progress:
            icon = icons.get(tp.status, "[?]  ")
            lines.append(f"  {icon} {tp.task_id}: {tp.task_title}")
            for ev in tp.evidence[:2]:
                lines.append(f"         > {ev[:60]}")

    lines.append(SEP)
    return "\n".join(lines)
