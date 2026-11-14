"""Run only against an explicitly supplied test environment."""

import argparse
import asyncio
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass

import httpx

TEXT = "Kubernetes schedules workloads. Metrics guide capacity."


@dataclass
class Sample:
    latency_s: float
    ttft_s: float | None
    output_tokens: int


@dataclass
class LevelResult:
    concurrency: int
    requests: int
    failures: int
    median_latency_s: float | None
    p95_latency_s: float | None
    median_ttft_s: float | None
    aggregate_output_tok_s: float


def completion_tokens(usage: dict) -> int:
    tokens = usage.get("completion_tokens")
    if type(tokens) is not int or tokens < 0:
        raise ValueError("Missing or invalid completion token usage")
    return tokens


class StreamParser:
    """Read one-line data events; token counts come only from final usage."""

    def __init__(self):
        self.ttft_s = None
        self.output_tokens = None
        self.done = False

    def feed(self, line: str, elapsed_s: float):
        if not line.startswith("data:"):
            return
        data = line[5:].strip()
        if not data:
            return
        if self.done:
            raise ValueError("Data after stream completion")
        if data == "[DONE]":
            self.done = True
            return
        event = json.loads(data)
        if not isinstance(event, dict) or "error" in event:
            raise ValueError("Invalid stream event")
        for choice in event.get("choices", []):
            delta = choice.get("delta", {})
            if self.ttft_s is None and (delta.get("content") or delta.get("reasoning_content")):
                self.ttft_s = elapsed_s
        usage = event.get("usage")
        if usage is not None:
            self.output_tokens = completion_tokens(usage)

    def finish(self, elapsed_s: float) -> Sample:
        if not self.done or self.output_tokens is None:
            raise ValueError("Incomplete stream or missing usage")
        if self.output_tokens > 0 and self.ttft_s is None:
            raise ValueError("No output token observed")
        return Sample(elapsed_s, self.ttft_s, self.output_tokens)


def summarize_level(
    concurrency: int, requests: int, samples: list[Sample], elapsed_s: float
) -> LevelResult:
    latencies = sorted(sample.latency_s for sample in samples)
    ttfts = [sample.ttft_s for sample in samples if sample.ttft_s is not None]
    return LevelResult(
        concurrency=concurrency,
        requests=requests,
        failures=requests - len(samples),
        median_latency_s=statistics.median(latencies) if latencies else None,
        p95_latency_s=latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        median_ttft_s=statistics.median(ttfts) if ttfts else None,
        aggregate_output_tok_s=sum(sample.output_tokens for sample in samples) / elapsed_s,
    )


def recommended_concurrency(levels: list[LevelResult]) -> int | None:
    if not levels:
        return None
    baseline = levels[0]
    recommendation = (
        baseline.concurrency
        if baseline.failures == 0 and baseline.aggregate_output_tok_s > 0
        else None
    )
    for previous, current in zip(levels, levels[1:], strict=False):
        if (
            previous.failures == current.failures == 0
            and previous.aggregate_output_tok_s > 0
            and current.aggregate_output_tok_s / previous.aggregate_output_tok_s >= 1.10
        ):
            recommendation = current.concurrency
    return recommendation


async def request_sample(client: httpx.AsyncClient, url: str, target: str) -> Sample:
    start = time.monotonic()
    if target == "app":
        response = await client.post(url + "/summarize", json={"text": TEXT, "max_tokens": 128})
        response.raise_for_status()
        tokens = completion_tokens(response.json())
        return Sample(time.monotonic() - start, None, tokens)
    parser = StreamParser()
    async with client.stream(
        "POST",
        url + "/v1/chat/completions",
        json={
            "model": "gemma4-summary",
            "messages": [{"role": "user", "content": TEXT}],
            "max_tokens": 128,
            "stream": True,
            "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},
        },
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            parser.feed(line, time.monotonic() - start)
    return parser.finish(time.monotonic() - start)


async def run_level(
    client: httpx.AsyncClient, url: str, target: str, concurrency: int, requests: int
) -> LevelResult:
    semaphore = asyncio.Semaphore(concurrency)
    samples = []

    async def one():
        async with semaphore:
            try:
                samples.append(await request_sample(client, url, target))
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
                # Failed and incomplete responses contribute no successful token usage.
                pass

    start = time.monotonic()
    await asyncio.gather(*(one() for _ in range(requests)))
    return summarize_level(concurrency, requests, samples, time.monotonic() - start)


async def run(url: str, target: str, concurrencies: list[int], requests: int) -> int:
    levels = []
    async with httpx.AsyncClient(timeout=180) as client:
        for concurrency in concurrencies:
            result = await run_level(client, url, target, concurrency, requests)
            levels.append(result)
            print(json.dumps(asdict(result)), flush=True)
    recommendation = recommended_concurrency(levels)
    label = recommendation if recommendation is not None else "unavailable"
    print(f"recommended concurrency: {label}")
    return int(any(level.failures for level in levels))


def concurrency_list(value: str) -> list[int]:
    try:
        levels = [int(item) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use comma-separated positive integers") from exc
    if not levels or any(level < 1 for level in levels) or levels != sorted(set(levels)):
        raise argparse.ArgumentTypeError(
            "Concurrency levels must be positive and strictly increasing"
        )
    return levels


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--target", choices=("model", "app"), required=True)
    parser.add_argument("--concurrency", type=concurrency_list, default=concurrency_list("1,2,4"))
    parser.add_argument("--requests", type=int, default=10)
    args = parser.parse_args()
    if args.requests < max(args.concurrency):
        parser.error("requests must be at least the highest concurrency")
    raise SystemExit(
        asyncio.run(
            run(
                args.url.rstrip("/"),
                args.target,
                args.concurrency,
                args.requests,
            )
        )
    )
