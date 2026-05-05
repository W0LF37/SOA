from __future__ import annotations


if __name__ == "__main__":
    from src.kb.seed_data import seed_kb
    from src.kb.vector_store import KnowledgeBase

    kb = KnowledgeBase()
    n = seed_kb(kb)
    print(f"Seeded {n} documents into Knowledge Base at storage/chroma/")
    print(f"Total documents in KB: {kb.count()}")
