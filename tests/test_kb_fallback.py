from __future__ import annotations

from src.pipelines import doc_to_tasks


def test_load_knowledge_base_for_pipeline_continues_when_kb_is_unavailable(monkeypatch) -> None:
    import src.kb.vector_store as vector_store

    reset_called = False

    def broken_get_kb():
        raise AttributeError("'RustBindingsAPI' object has no attribute 'bindings'")

    def fake_reset_kb() -> None:
        nonlocal reset_called
        reset_called = True

    messages: list[str] = []
    monkeypatch.setattr(vector_store, "get_kb", broken_get_kb)
    monkeypatch.setattr(vector_store, "reset_kb", fake_reset_kb)
    monkeypatch.setattr(doc_to_tasks, "_safe_print", messages.append)

    kb, count = doc_to_tasks._load_knowledge_base_for_pipeline(True)

    assert kb is None
    assert count == 0
    assert reset_called is True
    assert any("Knowledge Base unavailable" in message for message in messages)
