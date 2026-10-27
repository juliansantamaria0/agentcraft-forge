import json
from contextlib import closing

import pytest

pytest.importorskip("langchain_qdrant")

from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient


class TopicEmbeddings(Embeddings):
    model = "synthetic-topics-v1"

    def __init__(self):
        self.queries = []

    @staticmethod
    def vector(text):
        if "urgentes" in text.lower():
            return [1.0, 0.0, 0.0]
        if "vacaciones" in text.lower():
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_documents(self, texts):
        return [self.vector(text) for text in texts]

    def embed_query(self, text):
        self.queries.append(text)
        return self.vector(text)


@pytest.fixture
def conversation(runtime_project, tmp_path):
    target, load = runtime_project("rag")
    service = load("rag.service")
    embeddings = TopicEmbeddings()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "urgentes.md").write_text(
        "Solicitudes urgentes: plazo cuatro horas. Si se supera, escalar al supervisor.",
        encoding="utf-8",
    )
    (corpus / "vacaciones.md").write_text(
        "Vacaciones: solicitar con quince días de anticipación.", encoding="utf-8"
    )

    class Model:
        def __init__(self):
            self.messages = []

        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            self.messages.append(messages)
            evidence = json.loads(messages[1].content)["evidence"][0]
            return service.RagAnswer(
                answer=evidence["text"], citations=[evidence["id"]], abstained=False
            )

    with closing(QdrantClient(location=":memory:")) as client:
        load("rag.ingest").ingest(client, "conversation", embeddings, corpus, "demo")
        vectors = load("rag.store").vector_store(client, "conversation", embeddings)
        embeddings.queries.clear()
        yield target, load, service, vectors, embeddings, Model(), load(
            "settings"
        ).Settings()


def test_simple_followup_recovers_previous_question_without_extra_model(conversation):
    _, _, service, store, embeddings, model, settings = conversation
    history = []
    first = service.answer_turn(
        store,
        model,
        "¿Cuál es el plazo de solicitudes urgentes?",
        history,
        "Consultar políticas",
        settings,
    )
    second = service.answer_turn(
        store,
        model,
        "¿Y qué pasa si se supera?",
        history,
        "Consultar políticas",
        settings,
    )
    assert first["retrieval_mode"] == "standalone"
    assert second["retrieval_mode"] == "previous_question"
    assert second["sources"] == {"S1": "urgentes.md"}
    assert "supervisor" in second["answer"]
    assert len(embeddings.queries) == len(model.messages) == 2
    assert "solicitudes urgentes" in embeddings.queries[1]
    assert "supervisor" not in embeddings.queries[1]


def test_topic_switch_uses_current_question_without_polluting_retrieval(conversation):
    _, _, service, store, embeddings, model, settings = conversation
    history = []
    service.answer_turn(
        store,
        model,
        "¿Cuál es el plazo de solicitudes urgentes?",
        history,
        "Consultar políticas",
        settings,
    )
    current = "Ahora, ¿cuál es la política de vacaciones?"
    result = service.answer_turn(
        store, model, current, history, "Consultar políticas", settings
    )
    assert embeddings.queries[-1] == current
    assert result["retrieval_mode"] == "standalone"
    assert result["sources"] == {"S1": "vacaciones.md"}


def test_explicit_conditional_question_does_not_require_previous_turn(conversation):
    _, _, service, store, embeddings, model, settings = conversation
    question = "¿Qué pasa si se supera el plazo de solicitudes urgentes?"
    result = service.answer_turn(
        store, model, question, [], "Consultar políticas", settings
    )
    assert result["retrieval_mode"] == "standalone"
    assert embeddings.queries == [question]
    assert not result["abstained"]


@pytest.mark.parametrize(
    "prior,question",
    [
        (None, "¿Y qué pasa si se supera?"),
        ("¿Cuál es el plazo de solicitudes urgentes?", "¿Y eso?"),
        (
            "¿Qué plazos tienen las solicitudes urgentes y las vacaciones?",
            "¿Y si se supera?",
        ),
        ("¿Y qué pasa si se supera?", "¿Y si se incumple?"),
    ],
)
def test_ambiguous_reference_requires_clarification_without_provider(
    conversation, prior, question
):
    _, _, service, store, embeddings, model, settings = conversation
    history = (
        [{"question": prior, "answer_excerpt": "dato no autorizado como evidencia"}]
        if prior
        else []
    )
    result = service.answer_turn(
        store, model, question, history, "Consultar políticas", settings
    )
    assert result["abstained"] and result["citations"] == []
    assert result["retrieval_mode"] == "clarification_required"
    assert not embeddings.queries and not model.messages


def test_disabled_history_and_truncated_anchor_never_infer_reference(conversation):
    _, _, service, store, embeddings, model, settings = conversation
    for configured in [
        settings.model_copy(update={"history_turns": 0}),
        settings.model_copy(update={"max_history_chars": 10}),
    ]:
        history = []
        service.answer_turn(
            store,
            model,
            "¿Cuál es el plazo de solicitudes urgentes?",
            history,
            "Consultar políticas",
            configured,
        )
        previous_calls = len(embeddings.queries)
        result = service.answer_turn(
            store, model, "¿Y si se supera?", history, "Consultar políticas", configured
        )
        assert result["retrieval_mode"] == "clarification_required"
        assert len(embeddings.queries) == previous_calls


def test_worker_evaluates_followup_and_topic_switch_in_one_snapshot(
    conversation, tmp_path, monkeypatch
):
    from agentcraft_forge.evaluation import grade, load_suite

    target, load, _, _, _, model, _ = conversation
    worker = load("evaluate")
    monkeypatch.setattr(worker, "model_with_usage", lambda *args: model)
    monkeypatch.setattr(
        worker, "embeddings_with_usage", lambda *args: TopicEmbeddings()
    )
    suite = load_suite(target / "evals/smoke.json")
    spec = json.loads((target / "agentcraft.json").read_text(encoding="utf-8"))
    for case in [c for c in suite.cases if c.turns]:
        root = tmp_path / case.id
        root.mkdir()
        response = worker.execute(
            spec,
            {
                "case": case.model_dump(),
                "priced_models": ["gpt-4.1-mini", "text-embedding-3-small"],
            },
            root,
            [],
            {"known": True, "started": 0, "finished": 0},
        )
        assert len(response["turn_results"]) == len(case.turns)
        assert all(item["passed"] for item in grade(case, response))
    assert not (target / ".data").exists()


def test_interactive_runner_preserves_one_followup_between_queries(
    conversation, tmp_path, monkeypatch, capsys
):
    target, load, _, _, _, model, settings = conversation
    corpus = tmp_path / "runner-corpus"
    corpus.mkdir()
    (corpus / "urgentes.md").write_text(
        "Solicitudes urgentes: plazo cuatro horas. Si se supera, escalar al supervisor.",
        encoding="utf-8",
    )
    path = tmp_path / "runner-vectors"
    embeddings = TopicEmbeddings()
    with closing(QdrantClient(path=str(path))) as client:
        load("rag.ingest").ingest(client, "conversation", embeddings, corpus, "demo")
    embeddings.queries.clear()
    configured = settings.model_copy(
        update={"collection": "conversation", "local_path": path}
    )
    monkeypatch.setattr(load("settings"), "load_settings", lambda *args: configured)
    monkeypatch.setattr(load("providers"), "chat_model", lambda *args: model)
    monkeypatch.setattr(load("providers"), "embeddings_model", lambda *args: embeddings)
    prompts = iter(
        [
            "¿Cuál es el plazo de solicitudes urgentes?",
            "¿Y qué pasa si se supera?",
            "salir",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *args: next(prompts))
    assert load("runner").main(["--root", str(target)]) == 0
    output = capsys.readouterr()
    decoder = json.JSONDecoder()
    text = output.out[output.out.index("{") :]
    answers = []
    while text.strip():
        answer, end = decoder.raw_decode(text.lstrip())
        answers.append(answer)
        text = text.lstrip()[end:]
    assert [answer["retrieval_mode"] for answer in answers] == [
        "standalone",
        "previous_question",
    ]
    assert len(embeddings.queries) == len(model.messages) == 2
    assert "supervisor" in answers[1]["answer"]
    assert "urgentes" not in output.err
