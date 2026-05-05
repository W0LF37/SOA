from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from src.core.runtime_paths import prepare_writable_directory_path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

_instance: "KnowledgeBase | None" = None


def get_kb(persist_dir: str | None = None, collection_name: str = "pm_knowledge") -> "KnowledgeBase":
    global _instance
    if _instance is None:
        _instance = KnowledgeBase(persist_dir=persist_dir, collection_name=collection_name)
    return _instance


def reset_kb() -> None:
    global _instance
    _instance = None


class KnowledgeBase:
    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str = "pm_knowledge",
    ):
        if persist_dir is None:
            persist_dir = str(
                prepare_writable_directory_path(
                    PROJECT_ROOT,
                    "storage/chroma",
                    anchor_filenames=("chroma.sqlite3",),
                )
            )
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.collection = self.client.get_or_create_collection(collection_name)

    def add_documents(self, docs: list[dict]) -> None:
        if not docs:
            return
        ids        = [str(doc["id"]) for doc in docs]
        texts      = [str(doc["text"]) for doc in docs]
        # ✅ احفظ كل metadata وليس فقط category
        metadatas  = [
            {k: v for k, v in doc.get("metadata", {}).items()
             if isinstance(v, (str, int, float, bool))}
            for doc in docs
        ]
        embeddings = self.model.encode(texts).tolist()
        self.collection.upsert(
            ids=ids, documents=texts,
            metadatas=metadatas, embeddings=embeddings,
        )

    def query(self, text: str, n_results: int = 3) -> list[dict]:
        embedding = self.model.encode([text]).tolist()[0]
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]
        rows: list[dict] = []
        for doc, meta, dist in zip(documents[0], metadatas[0], distances[0]):
            rows.append({
                "text":     doc,
                "metadata": meta,          # ✅ كل الـ metadata مش فقط category
                "category": meta.get("category", ""),
                "distance": float(dist),
            })
        return rows

    def count(self) -> int:
        return self.collection.count()
