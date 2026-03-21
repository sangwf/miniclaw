from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


DEFAULT_MODEL = "gpt-5.4-mini"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None


@dataclass(frozen=True)
class ModelOutput:
    text: str
    tool_calls: list[ToolCall]
    usage: Usage | None = None


class LLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelOutput:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            request["tools"] = tools

        response = self.client.chat.completions.create(**request)
        message = response.choices[0].message

        content = message.content or ""
        tool_calls: list[ToolCall] = []
        for tool_call in message.tool_calls or []:
            tool_calls.append(
                ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                )
            )

        usage_data = None
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt_tokens_details = getattr(usage, "prompt_tokens_details", None)
            usage_data = Usage(
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
                cached_tokens=getattr(prompt_tokens_details, "cached_tokens", None),
            )

        return ModelOutput(text=content, tool_calls=tool_calls, usage=usage_data)
