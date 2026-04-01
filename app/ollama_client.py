from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from ollama import Client
from pydantic import BaseModel, Field

from app.settings import Settings


class ToolCallSpec(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatTurn(BaseModel):
    content: str = ""
    message: dict[str, Any]
    tool_calls: list[ToolCallSpec] = Field(default_factory=list)


class LLMGateway(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Any] | None = None,
        format: dict[str, Any] | str | None = None,
    ) -> ChatTurn: ...


class OllamaGateway:
    def __init__(self, settings: Settings):
        self._client = Client(
            host=settings.ollama_host,
            timeout=settings.ollama_timeout_seconds,
        )

    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Any] | None = None,
        format: dict[str, Any] | str | None = None,
    ) -> ChatTurn:
        response = self._client.chat(
            model=model,
            messages=list(messages),
            tools=list(tools) if tools else None,
            stream=False,
            format=format,
            options={"temperature": 0},
        )

        message = response.message.model_dump(exclude_none=True)
        tool_calls = [
            ToolCallSpec(
                name=tool_call.function.name,
                arguments=dict(tool_call.function.arguments or {}),
            )
            for tool_call in (response.message.tool_calls or [])
        ]
        return ChatTurn(
            content=response.message.content or "",
            message=message,
            tool_calls=tool_calls,
        )
