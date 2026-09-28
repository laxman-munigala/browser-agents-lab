"""Stagehand → OpenRouter adapter.

Stagehand's built-in model list covers OpenAI, Anthropic, Google, Groq and
Cerebras. Anything else plugs in as a callback: Stagehand hands us a
provider-neutral request (messages, optional tools, optional JSON schema) and
expects a provider-neutral reply. This module translates both ways to the
OpenAI chat-completions format that OpenRouter speaks, and keeps a running
token count for the scoreboard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from stagehand._generated import models as m

from common import llm


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0


usage = Usage()


def _blocks(content: Any) -> list[Any]:
    items = content if isinstance(content, list) else [content]
    return [getattr(b, "root", b) for b in items]


def _to_openai(params: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if params.system_prompt:
        out.append({"role": "system", "content": params.system_prompt})
    for msg in params.messages:
        role = str(getattr(msg.role, "value", msg.role))
        parts: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        for b in _blocks(msg.content):
            if b.type == "text":
                parts.append({"type": "text", "text": b.text})
            elif b.type == "image":
                parts.append({"type": "image_url", "image_url": {"url": f"data:{b.mime_type};base64,{b.data}"}})
            elif b.type == "tool_use":
                tool_calls.append({
                    "id": b.id, "type": "function",
                    "function": {"name": b.name, "arguments": json.dumps(b.input)},
                })
            elif b.type == "tool_result":
                text = "\n".join(getattr(c, "root", c).text for c in b.content if getattr(getattr(c, "root", c), "type", "") == "text")
                if b.structured_content is not None:
                    text = text or json.dumps(b.structured_content)
                out.append({"role": "tool", "tool_call_id": b.tool_use_id, "content": text or ""})
        if parts or tool_calls:
            entry: dict[str, Any] = {"role": role, "content": parts or ""}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
    return out


async def generate(params: Any) -> Any:
    client = AsyncOpenAI(base_url=llm.BASE_URL, api_key=llm.api_key())
    kwargs: dict[str, Any] = {"model": llm.model(), "messages": _to_openai(params)}
    if params.temperature is not None:
        kwargs["temperature"] = params.temperature
    if params.stop_sequences:
        kwargs["stop"] = params.stop_sequences

    structured = isinstance(params, m.LLMStructuredGenerateParams)
    if structured:
        rf = params.response_format
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": rf.name, "schema": rf.schema_ or {"type": "object"}, "strict": False},
        }
    elif params.tools:
        kwargs["tools"] = [
            {"type": "function", "function": {
                "name": t.name, "description": t.description or "",
                "parameters": t.input_schema.model_dump(by_alias=True, exclude_none=True)
                if hasattr(t.input_schema, "model_dump") else t.input_schema,
            }}
            for t in params.tools
        ]
        mode = getattr(getattr(params.tool_choice, "mode", None), "value", None)
        if mode:
            kwargs["tool_choice"] = mode

    resp = await client.chat.completions.create(**kwargs)
    await client.close()
    choice = resp.choices[0]
    u = resp.usage
    usage.calls += 1
    if u:
        usage.tokens_in += u.prompt_tokens or 0
        usage.tokens_out += u.completion_tokens or 0
    llm_usage = m.LLMUsage(
        input_tokens=(u.prompt_tokens or 0) if u else 0,
        output_tokens=(u.completion_tokens or 0) if u else 0,
        total_tokens=(u.total_tokens or 0) if u else 0,
    )
    text = choice.message.content or ""

    if structured:
        try:
            data = json.loads(text)
        except ValueError:
            start, end = text.find("{"), text.rfind("}")
            data = json.loads(text[start : end + 1]) if start != -1 else None
        return m.LLMStructuredGenerateResult(
            role=m.LLMRole.assistant,
            content=[m.LLMTextContent(type="text", text=text)],
            stop_reason=choice.finish_reason,
            usage=llm_usage,
            output_format="json_schema",
            structured_content=data,
        )

    blocks: list[Any] = []
    if text:
        blocks.append(m.LLMTextContent(type="text", text=text))
    for call in choice.message.tool_calls or []:
        blocks.append(m.LLMToolUseContent(
            type="tool_use", id=call.id, name=call.function.name,
            input=json.loads(call.function.arguments or "{}"),
        ))
    return m.LLMMessageGenerateResult(
        role=m.LLMRole.assistant,
        content=blocks or [m.LLMTextContent(type="text", text="")],
        stop_reason=choice.finish_reason,
        usage=llm_usage,
        output_format="text",
    )
