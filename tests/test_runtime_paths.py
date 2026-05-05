from __future__ import annotations

from pathlib import Path

from src.core import runtime_paths


def test_resolve_writable_shared_input_path_falls_back_from_project_data(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))

    primary = project_root / "data" / "processed" / "api_input.txt"
    fallback = appdata / "CritiPlan" / "runtime" / "data" / "processed" / "api_input.txt"

    monkeypatch.setattr(
        runtime_paths,
        "_can_write_to_file_path",
        lambda path: path.resolve(strict=False) == fallback.resolve(strict=False),
    )

    assert runtime_paths.resolve_writable_shared_input_path(project_root) == fallback
    assert primary in runtime_paths.iter_readable_shared_input_paths(project_root)


def test_shared_input_candidates_deduplicate_runtime_dir(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setenv("CRITIPLAN_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    candidates = runtime_paths.shared_input_candidates(project_root)

    assert candidates[0] == project_root / "data" / "processed" / "api_input.txt"
    assert candidates[1] == runtime_dir / "data" / "processed" / "api_input.txt"
    assert len(candidates) == len({candidate.resolve(strict=False) for candidate in candidates})


def test_prepare_writable_file_path_copies_legacy_file_to_runtime(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    legacy = project_root / "data" / "processed" / "tasks.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"tasks": []}', encoding="utf-8")

    appdata = tmp_path / "appdata"
    fallback = appdata / "CritiPlan" / "runtime" / "data" / "processed" / "tasks.json"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setattr(
        runtime_paths,
        "_can_write_to_file_path",
        lambda path: path.resolve(strict=False) == fallback.resolve(strict=False),
    )

    active = runtime_paths.prepare_writable_file_path(project_root, "data/processed/tasks.json")

    assert active == fallback
    assert active.read_text(encoding="utf-8") == '{"tasks": []}'


def test_prepare_writable_directory_path_copies_legacy_directory(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    legacy_dir = project_root / "storage" / "chroma"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "chroma.sqlite3").write_text("seed", encoding="utf-8")

    appdata = tmp_path / "appdata"
    fallback_dir = appdata / "CritiPlan" / "runtime" / "storage" / "chroma"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setattr(
        runtime_paths,
        "_can_write_to_directory",
        lambda path: path.resolve(strict=False) == fallback_dir.resolve(strict=False),
    )

    active = runtime_paths.prepare_writable_directory_path(
        project_root,
        "storage/chroma",
        anchor_filenames=("chroma.sqlite3",),
    )

    assert active == fallback_dir
    assert (active / "chroma.sqlite3").read_text(encoding="utf-8") == "seed"
