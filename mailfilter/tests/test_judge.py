"""The judge through the real Anthropic SDK, with Bedrock's HTTP answered offline."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from mailfilter.contract import Proposal
from mailfilter.errors import JudgeConfigError, JudgeFailed, JudgeUnavailable
from mailfilter.judge import MAX_TOKENS, OUTPUT_SCHEMA, SYSTEM_PROMPT, ClaudeJudge
from mailfilter.samples import BY_KEY

MODEL = "anthropic.claude-haiku-5-5"


def bedrock(handler: Callable[[httpx2.Request], httpx2.Response]) -> ClaudeJudge:
    client = anthropic.AnthropicBedrockMantle(
        aws_region="ap-south-1",
        skip_auth=True,
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return ClaudeJudge(client, MODEL)


def reply(content: list[dict[str, Any]], stop: str = "end_turn") -> httpx2.Response:
    body: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 120},
    }
    if stop == "refusal":
        body["stop_details"] = {"type": "refusal", "category": None, "explanation": "declined"}
    return httpx2.Response(200, json=body)


def answer_of(proposal: Proposal) -> list[dict[str, Any]]:
    return [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": proposal.model_dump_json()},
    ]


def test_the_request_is_haiku_in_mumbai_with_a_schema_and_cached_instructions() -> None:
    sent: dict[str, Any] = {}
    golden = BY_KEY["nimbus_drive"].golden

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent["url"] = str(request.url)
        sent["body"] = json.loads(request.content)
        return reply(answer_of(golden))

    assert bedrock(handler).judge("Received: ...\nFrom: x\nSubject: y") == golden
    assert sent["url"] == "https://bedrock-mantle.ap-south-1.api.aws/anthropic/v1/messages"
    body = sent["body"]
    assert body["model"] == MODEL and body["max_tokens"] == MAX_TOKENS
    assert body["system"] == [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
    ]
    assert body["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
    }
    assert body["messages"] == [{"role": "user", "content": "Received: ...\nFrom: x\nSubject: y"}]
    assert not {"temperature", "top_p", "top_k", "tools", "tool_choice"} & body.keys()


def test_the_instructions_never_change_between_calls() -> None:
    bodies: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.dumps(json.loads(request.content)["system"], sort_keys=True))
        return reply(answer_of(BY_KEY["webinar"].golden))

    judge = bedrock(handler)
    judge.judge("one")
    judge.judge("two")
    assert bodies[0] == bodies[1]


def test_the_schema_is_one_structured_outputs_accept() -> None:
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            assert not {"minLength", "maxLength", "minimum", "maximum", "pattern"} & node.keys()
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(OUTPUT_SCHEMA)
    assert set(OUTPUT_SCHEMA["properties"]) == set(Proposal.model_fields)


@pytest.mark.parametrize(
    ("content", "stop", "detail"),
    [
        ([], "refusal", "refusal"),
        ([{"type": "text", "text": "I can't help with that"}], "refusal", "refusal"),
        ([{"type": "text", "text": '{"kind": "plac'}], "max_tokens", "max_tokens"),
        ([{"type": "text", "text": "not json"}], "end_turn", "not_json"),
        ([{"type": "text", "text": '{"kind": "spam"}'}], "end_turn", "bad_shape"),
        ([{"type": "thinking", "thinking": "", "signature": "s"}], "end_turn", "no_text"),
    ],
)
def test_an_unusable_answer_fails_that_mail_only(
    content: list[dict[str, Any]], stop: str, detail: str
) -> None:
    judge = bedrock(lambda request: reply(content, stop))
    with pytest.raises(JudgeFailed) as raised:
        judge.judge("mail")
    assert raised.value.detail == detail
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, JudgeConfigError),
        (401, JudgeConfigError),
        (403, JudgeConfigError),
        (404, JudgeConfigError),
        (413, JudgeFailed),
        (429, JudgeUnavailable),
        (500, JudgeUnavailable),
        (503, JudgeUnavailable),
        (529, JudgeUnavailable),
    ],
)
def test_bedrock_failures_are_named(status: int, error: type[Exception]) -> None:
    judge = bedrock(
        lambda request: httpx2.Response(
            status, json={"type": "error", "error": {"type": "x", "message": "m"}}
        )
    )
    with pytest.raises(error):
        judge.judge("mail")


def test_a_network_failure_is_unavailable() -> None:
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    with pytest.raises(JudgeUnavailable):
        bedrock(down).judge("mail")


def test_a_validation_error_never_carries_mail_text_out() -> None:
    secret = "Ravi's marks are 41 out of 100"
    judge = bedrock(lambda request: reply([{"type": "text", "text": json.dumps({"kind": secret})}]))
    with pytest.raises(JudgeFailed) as raised:
        judge.judge("mail")
    assert secret not in str(raised.value) and raised.value.__cause__ is None
    assert raised.value.__suppress_context__
