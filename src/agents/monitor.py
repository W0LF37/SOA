from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

import numpy as np

from src.core.schemas import (
    CommitInfo,
    MonitorReport,
    RepositoryHotspot,
    TaskList,
    TaskProgress,
)

if TYPE_CHECKING:
    from src.llm.ollama_client import OllamaClient


class SemanticMatcher:
    """Semantic commit-to-task matcher using sentence-transformers first."""

    SIMILARITY_THRESHOLD = 0.65
    _FALLBACK_STOP_WORDS: frozenset[str] = frozenset({
        "a", "an", "and", "add", "build", "create", "deliver", "feature",
        "for", "implement", "in", "module", "of", "on", "task", "the",
        "to", "workflow", "handling", "management", "service", "system",
    })
    _CONCEPT_ALIASES: dict[str, str] = {
        "auth": "authentication",
        "authenticate": "authentication",
        "authentication": "authentication",
        "authorization": "authentication",
        "authorize": "authentication",
        "authorized": "authentication",
        "credential": "authentication",
        "credentials": "authentication",
        "jwt": "authentication",
        "login": "authentication",
        "logins": "authentication",
        "password": "authentication",
        "passwords": "authentication",
        "session": "authentication",
        "sessions": "authentication",
        "signin": "authentication",
        "signon": "authentication",
        "token": "authentication",
        "tokens": "authentication",
    }

    def __init__(self) -> None:
        self.model = None
        self._task_embeddings: dict[str, list[float]] = {}
        self._task_concepts: dict[str, set[str]] = {}
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(
                "all-MiniLM-L6-v2",
                local_files_only=True,
            )
        except Exception:  # noqa: BLE001
            self.model = None

    def precompute(self, task_list: TaskList) -> None:
        texts = [f"{t.title}. {t.description}" for t in task_list.tasks]
        self._task_concepts = {
            t.id: self._concept_tokens(texts[i])
            for i, t in enumerate(task_list.tasks)
        }
        if self.model is None:
            self._task_embeddings = {}
            return
        embeddings = self.model.encode(texts, show_progress_bar=False)
        self._task_embeddings = {
            t.id: embeddings[i].tolist()
            for i, t in enumerate(task_list.tasks)
        }

    def similarity(self, commit_text: str, task_id: str) -> float:
        task_concepts = self._task_concepts.get(task_id, set())
        if self.model is None or task_id not in self._task_embeddings:
            return self._fallback_similarity(commit_text, task_concepts)
        try:
            commit_emb = self.model.encode([commit_text], show_progress_bar=False)[0]
            task_emb = np.array(self._task_embeddings[task_id])
            commit_emb = np.array(commit_emb)
            denom = np.linalg.norm(commit_emb) * np.linalg.norm(task_emb)
            if denom < 1e-8:
                return self._fallback_similarity(commit_text, task_concepts)
            return float(np.dot(commit_emb, task_emb) / denom)
        except Exception:  # noqa: BLE001
            return self._fallback_similarity(commit_text, task_concepts)

    def matches(self, commit_text: str, task_id: str) -> bool:
        return self.similarity(commit_text, task_id) >= self.SIMILARITY_THRESHOLD

    def _concept_tokens(self, text: str) -> set[str]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        concepts: set[str] = set()
        for token in tokens:
            concept = self._CONCEPT_ALIASES.get(token, token)
            if concept in self._FALLBACK_STOP_WORDS or len(concept) <= 2:
                continue
            concepts.add(concept)
        return concepts

    def _fallback_similarity(self, commit_text: str, task_concepts: set[str]) -> float:
        if not task_concepts:
            return 0.0
        commit_concepts = self._concept_tokens(commit_text)
        if not commit_concepts:
            return 0.0
        overlap = len(task_concepts & commit_concepts)
        if overlap == 0:
            return 0.0
        return overlap / min(len(task_concepts), len(commit_concepts))


@dataclass
class _MatchSignal:
    reasons: set[str]
    confidence: Literal["low", "medium", "high"]
    semantic_score: float
    keyword_overlap: int


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
    _HIGH_ALIGNMENT_THRESHOLD = 0.55
    _MEDIUM_ALIGNMENT_THRESHOLD = 0.32
    _CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
    _TRUSTED_CONFIDENCES = frozenset({"medium", "high"})

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
        sha_to_tasks = self._matched_tasks_by_commit(task_progress, trusted_only=True)

        completed = sum(1 for tp in task_progress if tp.status == "completed")
        in_progress = sum(1 for tp in task_progress if tp.status == "in_progress")
        not_started = sum(1 for tp in task_progress if tp.status == "not_started")
        needs_review = sum(1 for tp in task_progress if tp.status == "needs_review")

        return MonitorReport(
            overall_progress=round(overall, 3),
            tasks_tracked=len(task_progress),
            tasks_completed=completed,
            tasks_in_progress=in_progress,
            tasks_not_started=not_started,
            tasks_needs_review=needs_review,
            task_progress=task_progress,
            commits_analyzed=len(commit_objs),
            behind_schedule=behind,
            unmatched_commits=[
                commit for commit in commit_objs if commit.sha not in sha_to_tasks
            ],
            repository_hotspots=self._repository_hotspots(commit_objs, sha_to_tasks),
            tracked_repository=repo_path,
        )

    # ------------------------------------------------------------------ #
    # Git Reading                                                          #
    # ------------------------------------------------------------------ #

    def _read_git_commits(self, repo_path: str) -> list[CommitInfo]:
        """Read last 200 commits from git repo using subprocess."""
        git_executable = shutil.which("git")
        if git_executable is None:
            return self._read_git_commits_dulwich(repo_path)
        try:
            result = subprocess.run(
                [git_executable, "log", "--format=%H|||%s|||%ae|||%ci", "-n", "200"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return self._read_git_commits_dulwich(repo_path)

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
            return self._read_git_commits_dulwich(repo_path)

    def _read_git_commits_dulwich(self, repo_path: str) -> list[CommitInfo]:
        """Fallback git reader that works without a system git executable."""
        try:
            from dulwich.diff_tree import tree_changes
            from dulwich.repo import Repo

            repo = Repo(repo_path)
            commits: list[CommitInfo] = []
            for entry in repo.get_walker(max_entries=200):
                commit = entry.commit
                files_changed: list[str] = []
                parent_tree = repo[commit.parents[0]].tree if commit.parents else None
                for change in tree_changes(repo.object_store, parent_tree, commit.tree):
                    path_bytes = None
                    if change.new is not None and change.new.path is not None:
                        path_bytes = change.new.path
                    elif change.old is not None and change.old.path is not None:
                        path_bytes = change.old.path
                    if path_bytes:
                        files_changed.append(path_bytes.decode("utf-8", errors="replace"))

                author = commit.author.decode("utf-8", errors="replace")
                committed_at = datetime.fromtimestamp(
                    commit.commit_time,
                    tz=timezone.utc,
                ).isoformat()
                commits.append(
                    CommitInfo(
                        sha=commit.id.decode("ascii", errors="replace"),
                        message=commit.message.decode("utf-8", errors="replace").strip(),
                        author=author,
                        date=committed_at,
                        files_changed=files_changed,
                    )
                )
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

    def _extract_keywords(self, text: str) -> frozenset[str]:
        """Extract meaningful keywords from task text."""
        words = text.lower().replace("-", " ").replace("_", " ").split()
        return frozenset(w for w in words if w not in self._STOP_WORDS and len(w) > 2)

    def _task_keywords(self, task) -> frozenset[str]:  # noqa: ANN001
        return self._extract_keywords(f"{task.title} {task.description}")

    @staticmethod
    def _commit_haystack(commit: CommitInfo) -> str:
        return (commit.message + " " + " ".join(commit.files_changed)).lower()

    def _keyword_overlap_count(self, text: str, keywords: frozenset[str]) -> int:
        return sum(
            1
            for kw in keywords
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text)
        )

    def _commit_references_task(self, commit: CommitInfo, task) -> bool:  # noqa: ANN001
        text = self._commit_haystack(commit)
        task_patterns = [
            re.escape(task.id.lower()),
            re.escape(task.source.lower()),
        ]
        return any(
            re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text)
            for pattern in task_patterns
        )

    def _commit_matches_task(
        self, commit: CommitInfo, keywords: frozenset[str]
    ) -> bool:
        """Check if a commit message or files reference any task keyword."""
        text = self._commit_haystack(commit)
        overlap = self._keyword_overlap_count(text, keywords)
        if overlap >= 2:
            return True
        return overlap == 1 and len(keywords) <= 2

    def _is_noise_commit(self, commit: CommitInfo) -> bool:
        """Short/generic commit messages carry no signal for semantic matching."""
        title = commit.message.split("\n")[0].strip()
        return len(title) < 10 and not commit.files_changed

    def _semantic_score(self, commit: CommitInfo, task_id: str) -> float:
        if self._matcher is None or self._is_noise_commit(commit):
            return 0.0
        commit_text = commit.message + " " + " ".join(commit.files_changed)
        if not commit_text.strip():
            return 0.0
        try:
            score = self._matcher.similarity(commit_text, task_id)
        except Exception:  # noqa: BLE001
            return 0.0
        return max(0.0, min(1.0, score))

    def _classify_match_confidence(
        self,
        *,
        explicit_reference: bool,
        semantic_score: float,
        keyword_overlap: int,
    ) -> Literal["low", "medium", "high"] | None:
        if explicit_reference and semantic_score >= self._HIGH_ALIGNMENT_THRESHOLD:
            return "high"
        if not explicit_reference and semantic_score >= 0.72 and keyword_overlap >= 1:
            return "high"
        if explicit_reference and (
            semantic_score >= self._MEDIUM_ALIGNMENT_THRESHOLD or keyword_overlap >= 1
        ):
            return "medium"
        if keyword_overlap >= 2:
            return "medium"
        if explicit_reference:
            return "low"
        return None

    def _commit_task_signal(
        self,
        commit: CommitInfo,
        task,
        keywords: frozenset[str],  # noqa: ANN001
    ) -> _MatchSignal | None:
        explicit_reference = self._commit_references_task(commit, task)
        text = self._commit_haystack(commit)
        keyword_overlap = self._keyword_overlap_count(text, keywords)
        semantic_score = self._semantic_score(commit, task.id)
        confidence = self._classify_match_confidence(
            explicit_reference=explicit_reference,
            semantic_score=semantic_score,
            keyword_overlap=keyword_overlap,
        )
        if confidence is None:
            return None

        reasons: set[str] = set()
        if explicit_reference:
            reasons.add("task reference")
        if keyword_overlap >= 2:
            reasons.add("keyword")
        if semantic_score >= self._HIGH_ALIGNMENT_THRESHOLD:
            reasons.add("semantic")
        elif confidence == "low":
            reasons.add("needs review")
        elif semantic_score >= self._MEDIUM_ALIGNMENT_THRESHOLD:
            reasons.add("partial semantic")

        return _MatchSignal(
            reasons=reasons,
            confidence=confidence,
            semantic_score=semantic_score,
            keyword_overlap=keyword_overlap,
        )

    def _semantic_match_task_ids(
        self,
        commit: CommitInfo,
        task_list: TaskList,
    ) -> set[str]:
        if self._matcher is None or self._is_noise_commit(commit):
            return set()

        scores = [
            (self._semantic_score(commit, task.id), task.id)
            for task in task_list.tasks
        ]
        if not scores:
            return set()

        best_score, _ = max(scores, key=lambda item: item[0])
        if best_score < self._matcher.SIMILARITY_THRESHOLD:
            return set()

        return {
            task_id
            for score, task_id in scores
            if score >= self._matcher.SIMILARITY_THRESHOLD and (best_score - score) <= 0.08
        }

    def _map_commits_to_tasks(
        self, task_list: TaskList, commits: list[CommitInfo]
    ) -> list[TaskProgress]:
        task_keywords = {
            task.id: self._task_keywords(task)
            for task in task_list.tasks
        }
        commit_task_matches: dict[str, dict[str, _MatchSignal]] = {}
        for commit in commits:
            task_matches: dict[str, _MatchSignal] = {}
            for task in task_list.tasks:
                signal = self._commit_task_signal(commit, task, task_keywords[task.id])
                if signal is not None:
                    task_matches[task.id] = signal
            commit_task_matches[commit.sha] = task_matches

        results: list[TaskProgress] = []
        for task in task_list.tasks:
            matched: list[CommitInfo] = []
            matched_files: set[str] = set()
            match_reasons: set[str] = set()
            confidence: Literal["none", "low", "medium", "high"] = "none"
            best_alignment = 0.0
            for commit in commits:
                signal = commit_task_matches.get(commit.sha, {}).get(task.id)
                if signal is None:
                    continue
                matched.append(commit)
                matched_files.update(commit.files_changed)
                match_reasons.update(signal.reasons)
                best_alignment = max(best_alignment, signal.semantic_score)
                if self._CONFIDENCE_RANK[signal.confidence] > self._CONFIDENCE_RANK[confidence]:
                    confidence = signal.confidence

            n = len(matched)
            status: Literal["not_started", "in_progress", "completed", "needs_review"]
            evidence_note = None
            if n == 0:
                status = "not_started"
                estimate = 0.0
            else:
                all_words = set()
                for c in matched:
                    all_words.update(c.message.lower().split())
                has_done = bool(all_words & self._DONE_KEYWORDS)
                trusted_commit_count = sum(
                    1
                    for commit in matched
                    if commit_task_matches.get(commit.sha, {}).get(task.id) is not None
                    and commit_task_matches[commit.sha][task.id].confidence in self._TRUSTED_CONFIDENCES
                )

                if confidence == "low":
                    status = "needs_review"
                    estimate = min(0.35, 0.15 + (0.05 * n))
                    match_reasons.add("id-only evidence")
                    evidence_note = (
                        "Task ID was found, but the commit wording and changed files do not strongly align with this task."
                    )
                elif trusted_commit_count >= 2 or has_done:
                    status = "completed"
                    estimate = 1.0
                else:
                    status = "in_progress"
                    if confidence == "high":
                        estimate = 0.6
                    else:
                        estimate = 0.5
                    if confidence == "medium":
                        evidence_note = (
                            "Repository evidence is partially aligned; manual validation is recommended before treating this task as complete."
                        )

            results.append(
                TaskProgress(
                    task_id=task.id,
                    task_title=task.title,
                    status=status,
                    matched_commits=[c.sha for c in matched],
                    evidence=[c.message for c in matched],
                    matched_files=sorted(matched_files),
                    match_reasons=sorted(match_reasons),
                    evidence_confidence=confidence,
                    alignment_score=round(best_alignment, 3),
                    evidence_note=evidence_note,
                    completion_estimate=estimate,
                )
            )
        return results

    @staticmethod
    def _matched_tasks_by_commit(
        task_progress: list[TaskProgress],
        trusted_only: bool = False,
    ) -> dict[str, set[str]]:
        sha_to_tasks: dict[str, set[str]] = defaultdict(set)
        for progress in task_progress:
            if trusted_only and progress.evidence_confidence not in {"medium", "high"}:
                continue
            for sha in progress.matched_commits:
                sha_to_tasks[sha].add(progress.task_id)
        return sha_to_tasks

    @staticmethod
    def _repository_hotspots(
        commits: list[CommitInfo],
        sha_to_tasks: dict[str, set[str]],
        limit: int = 8,
    ) -> list[RepositoryHotspot]:
        hotspot_counts: dict[str, int] = defaultdict(int)
        hotspot_tasks: dict[str, set[str]] = defaultdict(set)

        for commit in commits:
            linked_tasks = sha_to_tasks.get(commit.sha, set())
            for path in commit.files_changed:
                hotspot_counts[path] += 1
                hotspot_tasks[path].update(linked_tasks)

        ranked_paths = sorted(
            hotspot_counts,
            key=lambda path: (-hotspot_counts[path], -len(hotspot_tasks[path]), path.lower()),
        )[:limit]
        return [
            RepositoryHotspot(
                path=path,
                commit_count=hotspot_counts[path],
                linked_task_ids=sorted(hotspot_tasks[path]),
            )
            for path in ranked_paths
        ]

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
        f"{report.tasks_not_started} not started, "
        f"{report.tasks_needs_review} needs review)",
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
            "needs_review": "[REV] ",
            "not_started": "[    ]",
        }
        for tp in report.task_progress:
            icon = icons.get(tp.status, "[?]  ")
            lines.append(f"  {icon} {tp.task_id}: {tp.task_title}")
            for ev in tp.evidence[:2]:
                lines.append(f"         > {ev[:60]}")

    lines.append(SEP)
    return "\n".join(lines)
