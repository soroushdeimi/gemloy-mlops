import argparse
import json

import httpx
import pytest
import respx

from loadtest.run import (
    LevelResult,
    Sample,
    StreamParser,
    concurrency_list,
    recommended_concurrency,
    run_level,
    summarize_level,
)


def level(concurrency, throughput, failures=0):
    return LevelResult(concurrency, 10, failures, 1, 1, 0.1, throughput)


@pytest.mark.parametrize(
    "levels,expected",
    [
        ([], None),
        ([level(1, 100)], 1),
        ([level(1, 100), level(2, 110), level(4, 120)], 2),
        ([level(1, 100), level(2, 109), level(4, 130)], 4),
        ([level(1, 100), level(2, 150, failures=1)], 1),
        ([level(1, 100, failures=1), level(2, 150)], None),
        ([level(1, 0), level(2, 0)], None),
        ([level(1, 100), level(2, 110), level(4, 121)], 4),
    ],
)
def test_recommendation_rule(levels, expected):
    assert recommended_concurrency(levels) == expected


def test_stream_parser_uses_first_content_and_final_usage():
    parser = StreamParser()
    parser.feed(": keepalive", 0.1)
    parser.feed('data: {"choices":[{"delta":{"role":"assistant","content":""}}]}', 0.2)
    parser.feed('data: {"choices":[{"delta":{"content":"First"}}]}', 0.5)
    parser.feed('data: {"choices":[{"delta":{"content":" second"}}]}', 0.7)
    parser.feed('data: {"choices":[],"usage":{"completion_tokens":7}}', 0.8)
    parser.feed("data: [DONE]", 0.9)
    assert parser.finish(1.0) == Sample(latency_s=1.0, ttft_s=0.5, output_tokens=7)


@pytest.mark.parametrize(
    "lines",
    [
        ['data: {"choices":[]}'],
        ["data: [DONE]"],
        ['data: {"usage":{"completion_tokens":true}}'],
        ['data: {"error":{"message":"failed"}}'],
        ["data: malformed"],
        ['data: {"usage":{"completion_tokens":2}}', "data: [DONE]"],
    ],
)
def test_incomplete_or_invalid_stream_is_failure(lines):
    parser = StreamParser()
    with pytest.raises(ValueError):
        for line in lines:
            parser.feed(line, 1.0)
        parser.finish(2.0)


def test_level_output_statistics():
    result = summarize_level(2, 4, [Sample(1, 0.2, 10), Sample(3, 0.6, 30)], 5)
    assert result.failures == 2
    assert result.median_latency_s == 2
    assert result.p95_latency_s == 3
    assert result.median_ttft_s == 0.4
    assert result.aggregate_output_tok_s == 8


@pytest.mark.parametrize("target", ["model", "app"])
@respx.mock
async def test_targets_and_output_parsing_offline(target):
    if target == "model":
        body = (
            'data: {"choices":[{"delta":{"content":"Summary"}}]}\n\n'
            'data: {"choices":[],"usage":{"completion_tokens":3}}\n\n'
            "data: [DONE]\n\n"
        )
        route = respx.post("http://test-model/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, text=body, headers={"content-type": "text/event-stream"}
            )
        )
    else:
        route = respx.post("http://test-model/summarize").mock(
            return_value=httpx.Response(200, json={"summary": "Summary", "completion_tokens": 3})
        )
    async with httpx.AsyncClient() as client:
        result = await run_level(client, "http://test-model", target, 1, 2)
    assert result.requests == 2
    assert result.failures == 0
    assert result.aggregate_output_tok_s > 0
    assert (result.median_ttft_s is not None) == (target == "model")
    assert route.call_count == 2
    if target == "model":
        payload = json.loads(route.calls[0].request.content)
        assert payload["model"] == "gemma4-summary"
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}


@pytest.mark.parametrize("value", ["0", "1,1", "2,1", "1,x", ""])
def test_invalid_concurrency_sweeps(value):
    with pytest.raises(argparse.ArgumentTypeError):
        concurrency_list(value)
