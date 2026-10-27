"""Compara operaciones de embeddings locales; no mide precios ni calidad de un LLM."""

import argparse
import importlib
import json
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from agentcraft_forge import __version__
from agentcraft_forge.generator import generate
from agentcraft_forge.planner import design
from agentcraft_forge.schema import Kind


class CountingEmbeddings(Embeddings):
    model = "local-fixture-v1"

    def __init__(self):
        self.operations = []

    def embed_documents(self, texts):
        self.operations.append(
            {"method": "documents", "characters": sum(map(len, texts))}
        )
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        self.operations.append({"method": "query", "characters": len(text)})
        return [1.0, 0.0, 0.0, 0.0]


def measure() -> dict:
    with TemporaryDirectory(prefix="agentcraft-retrieval-") as directory:
        root = generate(
            design("retrieval-check", "Consultar documentación interna", Kind.rag),
            Path(directory),
        )
        sys.path.insert(0, str(root / "src"))
        try:
            ingest = importlib.import_module("agent_app.rag.ingest").ingest
            store = importlib.import_module("agent_app.rag.store")
            retrieve = importlib.import_module("agent_app.rag.service").retrieve
            corpus = root / "corpus"
            corpus.mkdir()
            for number in range(2):
                (corpus / f"source-{number}.md").write_text(
                    "Política sintética: atención en cuatro horas.", encoding="utf-8"
                )
            embeddings = CountingEmbeddings()
            query = "¿Cuál es el plazo de atención?"
            with closing(QdrantClient(location=":memory:")) as client:
                ingest(client, "comparison", embeddings, corpus, "demo")
                embeddings.operations.clear()
                # Secuencia de consulta de 0.3.1: apertura + MMR + umbral aparte.
                previous = QdrantVectorStore(client, "comparison", embedding=embeddings)
                candidates = previous.max_marginal_relevance_search(
                    query, k=4, fetch_k=16, filter=store.tenant_filter("demo")
                )
                scored = previous.similarity_search_with_score(
                    query, k=16, filter=store.tenant_filter("demo"), score_threshold=0.2
                )
                allowed = {(d.metadata["source"], d.page_content) for d, _ in scored}
                previous_sources = sorted(
                    d.metadata["source"]
                    for d in candidates
                    if (d.metadata["source"], d.page_content) in allowed
                )
                baseline = list(embeddings.operations)
                embeddings.operations.clear()
                current = store.vector_store(client, "comparison", embeddings)
                result = retrieve(current, query, "demo", 4, 0.2)
                optimized = list(embeddings.operations)
                current_sources = sorted(d.metadata["source"] for d in result)
                if previous_sources != current_sources or len(result) != 2:
                    raise RuntimeError(
                        "La comparación no conservó las fuentes esperadas."
                    )
            return {
                "generator_version": __version__,
                "mode": "offline_real_qdrant_local_embeddings",
                "baseline": "Retrieval sequence from 0.3.1 / 9deb80f",
                "baseline_embedding_operations": baseline,
                "optimized_embedding_operations": optimized,
                "operation_reduction_percent": round(
                    100 * (1 - len(optimized) / len(baseline)), 2
                ),
                "retrieved_sources_equal": True,
                "sources": current_sources,
                "paid_model_calls": 0,
                "actual_tokens": None,
                "actual_cost_usd": None,
                "limitations": "Cuenta operaciones locales en una fixture, no ahorro porcentual de tokens, facturación ni calidad semántica.",
            }
        finally:
            sys.path.pop(0)
            for name in list(sys.modules):
                if name == "agent_app" or name.startswith("agent_app."):
                    del sys.modules[name]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(measure(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(result + "\n")
    print(result)


if __name__ == "__main__":
    main()
