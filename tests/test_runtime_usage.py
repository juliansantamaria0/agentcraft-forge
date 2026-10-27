import json

import pytest

pytest.importorskip("langchain_openai")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


def test_usage_is_observed_per_message_and_history_is_bounded(
    runtime_project, monkeypatch, capsys
):
    target, load = runtime_project("tools")
    observability = load("observability")
    captured = []

    class Model(FakeMessagesListChatModel):
        def bind_tools(self, tools):
            return self

        def _generate(self, messages, **kwargs):
            captured.append(messages)
            return super()._generate(messages, **kwargs)

    model = Model(
        responses=[
            AIMessage(
                content="respuesta-sintética-" * 20,
                usage_metadata={
                    "input_tokens": 30,
                    "output_tokens": 8,
                    "total_tokens": 38,
                },
            )
        ],
        callbacks=[observability.usage_callback("local-fixture")],
    )
    monkeypatch.setenv("HISTORY_TURNS", "1")
    monkeypatch.setenv("MAX_HISTORY_CHARS", "100")
    monkeypatch.setattr(load("providers"), "chat_model", lambda settings: model)
    prompts = iter(
        ["primera consulta", "segunda consulta", "tercera consulta", "salir"]
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
    assert len(answers) == 3
    for answer in answers:
        assert answer["usage"]["known"] is True
        assert answer["usage"]["chat_calls"] == 1
        assert answer["usage"]["by_model"] == {
            "local-fixture": {"input_tokens": 30, "output_tokens": 8}
        }
        assert answer["usage"]["cost_usd"] is None
        assert answer["usage"]["host_assistant_tokens"] is None
    contexts = [json.loads(messages[1].content) for messages in captured]
    assert contexts[0]["history"] == []
    assert len(contexts[2]["history"]) == 1
    assert contexts[2]["history"][0]["question"] == "segunda consulta"
    assert len(contexts[2]["history"][0]["answer_excerpt"]) <= 50
    assert "respuesta-sintética" not in output.err


def test_usage_missing_or_provider_failure_never_means_zero_cost(runtime_project):
    _, load = runtime_project("rag")
    module = load("observability")

    class Client:
        def create(self):
            return {"data": []}

    with module.usage_scope() as meter:
        assert module.metered_embeddings_client(
            Client(), "embeddings-local"
        ).create() == {"data": []}
    report = module.usage_report(meter)
    assert report["known"] is False and report["embedding_calls"] == 1
    assert report["cost_usd"] is None

    class Failed:
        def create(self):
            raise RuntimeError("provider-secret")

    with module.usage_scope() as meter:
        with pytest.raises(RuntimeError):
            module.metered_embeddings_client(Failed(), "embeddings-local").create()
    assert module.usage_report(meter)["known"] is False


def test_embedding_usage_counts_actual_provider_tokens(runtime_project):
    _, load = runtime_project("rag")
    module = load("observability")

    class Client:
        def create(self, **kwargs):
            return {"usage": {"total_tokens": 7}, "data": []}

    with module.usage_scope() as meter:
        client = module.metered_embeddings_client(Client(), "embeddings-local")
        client.create(input="private-text")
        client.create(input="other-private-text")
    report = module.usage_report(meter)
    assert report["known"] is True
    assert report["embedding_calls"] == 2
    assert report["by_model"] == {
        "embeddings-local": {"input_tokens": 14, "output_tokens": 0}
    }
    assert "private" not in json.dumps(report)


def test_provider_limits_and_dimensions_are_configured_without_network(runtime_project):
    from pydantic import SecretStr

    _, load = runtime_project("rag")
    settings = load("settings").Settings(
        api_key=SecretStr("synthetic-unused"), embedding_dimensions=256
    )
    providers = load("providers")
    assert providers.chat_model(settings).max_retries == 0
    assert providers.chat_model(settings).max_tokens == 1200
    assert providers.embeddings_model(settings).dimensions == 256
    with pytest.raises(ValueError):
        settings.model_validate({"history_turns": 3})
