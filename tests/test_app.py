import os
import subprocess
import sys
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app

URL = "http://vllm:8000/v1/chat/completions"
OK = {
    "choices": [{"message": {"content": "A short summary."}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MODEL_URL", "http://vllm:8000")
    monkeypatch.setattr("app.main.asyncio.sleep", AsyncMock())
    with TestClient(app) as client:
        yield client


@respx.mock
def test_success(client):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=OK))
    response = client.post("/summarize", json={"text": "Some text"})
    assert response.status_code == 200
    assert response.json() == {
        "summary": "A short summary.",
        "prompt_tokens": 10,
        "completion_tokens": 4,
    }
    assert route.call_count == 1
    assert "summarizer_tokens_total" in client.get("/metrics").text


@respx.mock
def test_timeout_no_retry(client):
    route = respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    assert client.post("/summarize", json={"text": "hello"}).status_code == 504
    assert route.call_count == 1


@respx.mock
def test_5xx_retry_then_fail(client):
    route = respx.post(URL).mock(return_value=httpx.Response(503))
    assert client.post("/summarize", json={"text": "hello"}).status_code == 502
    assert route.call_count == 3


@respx.mock
def test_retry_recovers(client):
    route = respx.post(URL).mock(side_effect=[httpx.Response(500), httpx.Response(200, json=OK)])
    assert client.post("/summarize", json={"text": "hello"}).status_code == 200
    assert route.call_count == 2


@respx.mock
def test_connect_retry(client):
    route = respx.post(URL).mock(side_effect=httpx.ConnectError("refused"))
    assert client.post("/summarize", json={"text": "hello"}).status_code == 502
    assert route.call_count == 3


@respx.mock
def test_4xx_no_retry(client):
    route = respx.post(URL).mock(return_value=httpx.Response(429))
    assert client.post("/summarize", json={"text": "hello"}).status_code == 502
    assert route.call_count == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": " "},
        {"text": "x" * 5001},
        {"text": "x", "max_tokens": 0},
        {"text": "x", "max_tokens": "16"},
    ],
)
def test_invalid_input(client, body):
    assert client.post("/summarize", json=body).status_code == 422


@respx.mock
def test_readiness_down(client):
    respx.get("http://vllm:8000/health").mock(return_value=httpx.Response(503))
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


@respx.mock
def test_readiness_up(client):
    respx.get("http://vllm:8000/health").mock(return_value=httpx.Response(200))
    assert client.get("/readyz").status_code == 200


@respx.mock
def test_malformed_upstream(client):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"choices": []}))
    assert client.post("/summarize", json={"text": "hello"}).status_code == 502


@pytest.mark.parametrize(
    "message",
    [
        "This model's maximum context length is 2048 tokens.",
        "Input token length exceeds the token limit.",
        "max_model_len exceeded",
    ],
)
@respx.mock
def test_context_length_error_is_validation_error(client, message):
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": {"message": message}},
        )
    )
    response = client.post("/summarize", json={"text": "token-heavy input"})
    assert response.status_code == 422
    assert response.json() == {"detail": "input too long for model context"}
    assert route.call_count == 1


@respx.mock
def test_other_upstream_400_stays_gateway_error(client):
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            400,
            json={"error": {"message": "Unsupported chat template parameter"}},
        )
    )
    response = client.post("/summarize", json={"text": "hello"})
    assert response.status_code == 502
    assert response.json() == {"detail": "model rejected request"}
    assert route.call_count == 1


@respx.mock
def test_default_input_boundary(client):
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=OK))
    assert client.post("/summarize", json={"text": "x" * 5000}).status_code == 200
    assert client.post("/summarize", json={"text": "x" * 5001}).status_code == 422
    assert route.call_count == 1


@pytest.mark.parametrize(
    "context,characters,expected",
    [
        (2048, 1000, 1000),
        (1024, 5000, 1568),
        (4096, 8000, 8000),
    ],
)
def test_environment_input_and_context_limits(context, characters, expected):
    settings_env = dict(
        os.environ, MODEL_CONTEXT_TOKENS=str(context), MAX_INPUT_CHARS=str(characters)
    )
    result = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "from app.main import SummaryRequest; "
            "print(SummaryRequest.model_json_schema()['properties']['text']['maxLength'])",
        ],
        env=settings_env,
        text=True,
    )
    assert int(result) == expected
