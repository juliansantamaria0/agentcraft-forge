from contextlib import closing

import pytest

pytest.importorskip(
    "langchain_qdrant", reason="Requiere las dependencias RAG del grupo dev."
)

from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client import models as qm


class EmbeddingsLocal(Embeddings):
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0, 0.0]


@pytest.fixture
def rag(runtime_project, tmp_path):
    target, load = runtime_project("rag")
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name in ("one", "two"):
        (corpus / f"{name}.md").write_text(
            f"Documento sintético {name}.", encoding="utf-8"
        )
    with closing(QdrantClient(":memory:")) as client:
        yield client, load("rag.ingest"), load(
            "rag.store"
        ), EmbeddingsLocal(), corpus, target


def test_interrupted_ingestion_cannot_be_queried(rag, monkeypatch):
    client, module, store, embeddings, corpus, _ = rag
    original = module.QdrantVectorStore.add_documents

    def partial(self, documents, ids):
        original(self, documents[:1], ids=ids[:1])
        raise RuntimeError("interrupción sintética")

    monkeypatch.setattr(module.QdrantVectorStore, "add_documents", partial)
    with pytest.raises(RuntimeError):
        module.ingest(client, "incomplete", embeddings, corpus, "a")
    assert client.count("incomplete", exact=True).count == 1
    with pytest.raises(ValueError, match="incompleta"):
        store.vector_store(client, "incomplete", embeddings)
    assert (
        not client.get_collection("incomplete").config.metadata["agentcraft"]["state"]
        == "ready"
    )


def test_ingestion_requires_all_chunks_before_publication(rag, monkeypatch):
    client, module, store, embeddings, corpus, _ = rag
    original = module.QdrantVectorStore.add_documents

    def silently_partial(self, documents, ids):
        return original(self, documents[:1], ids=ids[:1])

    monkeypatch.setattr(module.QdrantVectorStore, "add_documents", silently_partial)
    with pytest.raises(ValueError, match="incompleta"):
        module.ingest(client, "short", embeddings, corpus, "a")
    with pytest.raises(ValueError, match="incompleta"):
        store.vector_store(client, "short", embeddings)


def test_complete_snapshot_and_tenant_filter(rag):
    client, module, store, embeddings, corpus, _ = rag
    count = module.ingest(client, "complete", embeddings, corpus, "a")
    assert count == 2
    manifest = client.get_collection("complete").config.metadata["agentcraft"]
    assert manifest["state"] == "ready" and manifest["chunks"] == 2
    vectors = store.vector_store(client, "complete", embeddings)
    assert (
        len(vectors.similarity_search("consulta", filter=store.tenant_filter("a"))) == 2
    )
    assert not vectors.similarity_search("consulta", filter=store.tenant_filter("b"))
    with pytest.raises(ValueError, match="ya existe"):
        module.ingest(client, "complete", embeddings, corpus, "a")
    assert client.get_collection("complete").config.metadata["agentcraft"] == manifest


def test_legacy_collection_needs_reingestion_without_mutation(rag):
    client, _, store, embeddings, _, _ = rag
    client.create_collection(
        "legacy", vectors_config=qm.VectorParams(size=4, distance=qm.Distance.COSINE)
    )
    with pytest.raises(ValueError, match="incompleta"):
        store.vector_store(client, "legacy", embeddings)
    assert client.get_collection("legacy").config.metadata is None


def test_failure_before_ready_update_cannot_publish(rag, monkeypatch):
    client, module, store, embeddings, corpus, _ = rag

    def failed_update(*args, **kwargs):
        raise RuntimeError("interrupción al finalizar")

    monkeypatch.setattr(client, "update_collection", failed_update)
    with pytest.raises(RuntimeError):
        module.ingest(client, "unpublished", embeddings, corpus, "a")
    assert client.count("unpublished", exact=True).count == 2
    with pytest.raises(ValueError, match="incompleta"):
        store.vector_store(client, "unpublished", embeddings)


def test_matching_count_with_wrong_ids_cannot_publish(rag, monkeypatch):
    from uuid import uuid4

    client, module, store, embeddings, corpus, _ = rag
    original = module.QdrantVectorStore.add_documents

    def wrong_ids(self, documents, ids):
        return original(self, documents, ids=[str(uuid4()) for _ in ids])

    monkeypatch.setattr(module.QdrantVectorStore, "add_documents", wrong_ids)
    with pytest.raises(ValueError, match="inventario"):
        module.ingest(client, "wrong-ids", embeddings, corpus, "a")
    assert client.count("wrong-ids", exact=True).count == 2
    with pytest.raises(ValueError, match="incompleta"):
        store.vector_store(client, "wrong-ids", embeddings)


def test_deleted_chunk_invalidates_a_ready_snapshot(rag):
    client, module, store, embeddings, corpus, _ = rag
    module.ingest(client, "changed", embeddings, corpus, "a")
    records, _ = client.scroll("changed", limit=1)
    client.delete("changed", points_selector=qm.PointIdsList(points=[records[0].id]))
    with pytest.raises(ValueError, match="incompleta"):
        store.vector_store(client, "changed", embeddings)
