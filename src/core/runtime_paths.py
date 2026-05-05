from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def _unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in paths:
        normalized = candidate.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique


def runtime_root_candidates() -> list[Path]:
    candidates: list[Path] = []

    runtime_dir = os.getenv("CRITIPLAN_RUNTIME_DIR")
    if runtime_dir:
        candidates.append(Path(runtime_dir))

    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "CritiPlan" / "runtime")
    else:
        candidates.append(Path.home() / "AppData" / "Local" / "CritiPlan" / "runtime")

    candidates.append(Path(tempfile.gettempdir()) / "CritiPlan" / "runtime")
    return _unique_paths(candidates)


def artifact_file_candidates(project_root: Path, relative_path: str) -> list[Path]:
    rel = Path(relative_path)
    return _unique_paths([project_root / rel, *(root / rel for root in runtime_root_candidates())])


def artifact_dir_candidates(project_root: Path, relative_path: str) -> list[Path]:
    rel = Path(relative_path)
    return _unique_paths([project_root / rel, *(root / rel for root in runtime_root_candidates())])


def _can_write_to_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".__critiplan_write_test__.tmp"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _can_write_existing_file(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        return os.access(path, os.W_OK)
    except OSError:
        return False


def _can_write_to_file_path(path: Path) -> bool:
    return _can_write_to_directory(path.parent) and _can_write_existing_file(path)


def resolve_writable_file_path(project_root: Path, relative_path: str) -> Path:
    candidates = artifact_file_candidates(project_root, relative_path)
    for candidate in candidates:
        if _can_write_to_file_path(candidate):
            return candidate
    return candidates[0]


def resolve_writable_directory_path(
    project_root: Path,
    relative_path: str,
    anchor_filenames: tuple[str, ...] = (),
) -> Path:
    candidates = artifact_dir_candidates(project_root, relative_path)
    for candidate in candidates:
        if not _can_write_to_directory(candidate):
            continue
        if any((candidate / anchor).exists() and not _can_write_existing_file(candidate / anchor) for anchor in anchor_filenames):
            continue
        return candidate
    return candidates[0]


def _copy_file_if_needed(source: Path, target: Path) -> None:
    if target.exists() or not source.exists():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except OSError:
        pass


def _copy_dir_if_needed(source: Path, target: Path) -> None:
    if not source.exists():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)
    except OSError:
        pass


def prepare_writable_file_path(project_root: Path, relative_path: str) -> Path:
    legacy = project_root / Path(relative_path)
    active = resolve_writable_file_path(project_root, relative_path)
    if active.resolve(strict=False) != legacy.resolve(strict=False):
        _copy_file_if_needed(legacy, active)
    return active


def prepare_writable_directory_path(
    project_root: Path,
    relative_path: str,
    anchor_filenames: tuple[str, ...] = (),
) -> Path:
    legacy = project_root / Path(relative_path)
    active = resolve_writable_directory_path(project_root, relative_path, anchor_filenames=anchor_filenames)
    if active.resolve(strict=False) != legacy.resolve(strict=False):
        _copy_dir_if_needed(legacy, active)
    return active


def iter_readable_file_paths(project_root: Path, relative_path: str) -> list[Path]:
    active = prepare_writable_file_path(project_root, relative_path)
    ordered = [active, *artifact_file_candidates(project_root, relative_path)]
    return _unique_paths(ordered)


def shared_input_candidates(project_root: Path) -> list[Path]:
    return artifact_file_candidates(project_root, "data/processed/api_input.txt")


def resolve_writable_shared_input_path(project_root: Path) -> Path:
    return prepare_writable_file_path(project_root, "data/processed/api_input.txt")


def iter_readable_shared_input_paths(project_root: Path) -> list[Path]:
    return iter_readable_file_paths(project_root, "data/processed/api_input.txt")
