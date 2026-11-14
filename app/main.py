import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MODEL_CONTEXT_TOKENS = int(os.getenv("MODEL_CONTEXT_TOKENS", "2048"))
MAX_OUTPUT_TOKENS = 512
TEMPLATE_ALLOWANCE_TOKENS = 64
MAX_INPUT_CHARS = min(
    int(os.getenv("MAX_INPUT_CHARS", "5000")),
    int((MODEL_CONTEXT_TOKENS - MAX_OUTPUT_TOKENS - TEMPLATE_ALLOWANCE_TOKENS) * 3.5),
)
if MAX_INPUT_CHARS < 1:
    raise ValueError("Input limit and remaining model context must be positive")

REQUESTS = Counter("summarizer_requests_total", "HTTP requests", ["route", "status"])
LATENCY = Histogram(
    "summarizer_request_duration_seconds",
    "HTTP latency",
    ["route"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
ERRORS = Counter("summarizer_upstream_errors_total", "Upstream attempt errors", ["kind"])
TOKENS = Counter("summarizer_tokens_total", "Successful completion token usage", ["kind"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(
        base_url=os.getenv("MODEL_URL", "http://vllm:8000"),
        timeout=httpx.Timeout(120, connect=5, pool=5),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        follow_redirects=False,
    ) as client:
        app.state.client = client
        yield


app = FastAPI(lifespan=lifespan)


class SummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_INPUT_CHARS)
    ]
    max_tokens: int = Field(default=256, ge=16, le=MAX_OUTPUT_TOKENS, strict=True)


class SummaryResponse(BaseModel):
    summary: str
    prompt_tokens: int
    completion_tokens: int


@app.middleware("http")
async def instrument(request: Request, call_next):
    started = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        if request.url.path != "/metrics":
            route = request.scope.get("route")
            label = route.path if route else "unmatched"
            REQUESTS.labels(label, str(status)).inc()
            LATENCY.labels(label).observe(time.monotonic() - started)


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.get("/readyz")
async def ready(request: Request):
    try:
        response = await request.app.state.client.get("/health", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(503, "model unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


async def complete(client: httpx.AsyncClient, payload: dict) -> dict:
    for attempt in range(3):
        try:
            response = await client.post("/v1/chat/completions", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            ERRORS.labels("connect").inc()
            if attempt == 2:
                raise HTTPException(502, "model connection failed") from exc
        except httpx.TimeoutException as exc:
            ERRORS.labels("timeout").inc()
            raise HTTPException(504, "model timeout") from exc
        except httpx.HTTPError as exc:
            ERRORS.labels("transport").inc()
            raise HTTPException(502, "model transport failure") from exc
        else:
            if response.status_code >= 500:
                ERRORS.labels("5xx").inc()
                if attempt == 2:
                    raise HTTPException(502, "model unavailable")
            elif not response.is_success:
                ERRORS.labels("http").inc()
                message = response.text.lower()
                context_error = any(
                    phrase in message
                    for phrase in (
                        "context length",
                        "context_length",
                        "context window",
                        "max_model_len",
                        "too many tokens",
                        "token limit",
                        "token length",
                        "maximum number of tokens",
                    )
                )
                if response.status_code == 400 and context_error:
                    raise HTTPException(422, "input too long for model context")
                raise HTTPException(502, "model rejected request")
            else:
                try:
                    return response.json()
                except ValueError as exc:
                    ERRORS.labels("protocol").inc()
                    raise HTTPException(502, "invalid model response") from exc
        await asyncio.sleep(0.25 * 2**attempt)
    raise RuntimeError("retry loop exhausted")


@app.post("/summarize", response_model=SummaryResponse)
async def summarize(body: SummaryRequest, request: Request):
    try:
        async with asyncio.timeout(180):
            data = await complete(
                request.app.state.client,
                {
                    "model": os.getenv("MODEL_ALIAS", "gemma4-summary"),
                    "messages": [
                        {"role": "system", "content": "Summarize the supplied text concisely."},
                        {"role": "user", "content": body.text},
                    ],
                    "max_tokens": body.max_tokens,
                    "stream": False,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
    except TimeoutError as exc:
        ERRORS.labels("deadline").inc()
        raise HTTPException(504, "model deadline exceeded") from exc
    try:
        content = data["choices"][0]["message"]["content"]
        usage = data["usage"]
        prompt = usage["prompt_tokens"]
        completion = usage["completion_tokens"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("missing content")
        if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
            raise ValueError("invalid usage")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        ERRORS.labels("protocol").inc()
        raise HTTPException(502, "invalid model response") from exc
    TOKENS.labels("prompt").inc(prompt)
    TOKENS.labels("completion").inc(completion)
    return SummaryResponse(summary=content, prompt_tokens=prompt, completion_tokens=completion)
