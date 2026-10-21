"""Provider adapters (15.3 #5): the adapter is an interface, so a paid
provider is a configuration change. Each run records provider, model and
date."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


class ProviderError(Exception):
    def __init__(self, message: str, retry_after: float | None = None, fatal: bool = False) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.fatal = fatal


@dataclass
class Completion:
    message: dict[str, Any]
    tokens_in: int
    tokens_out: int
    headers: dict[str, str] = field(default_factory=dict)


class Provider(Protocol):
    name: str
    model: str

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_tokens: int) -> Completion: ...


class OpenAICompatible:
    """Groq by default; any OpenAI-compatible chat completions endpoint works."""

    def __init__(self, name: str = "groq", model: str = "openai/gpt-oss-20b", base_url: str | None = None, api_key: str | None = None, timeout: float = 60) -> None:
        self.name = name
        self.model = model
        self.base_url = (base_url or os.environ.get("REFERENCE_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("GROQ_API_KEY") or os.environ.get("REFERENCE_API_KEY_MODEL")
        self.http = httpx.Client(timeout=timeout)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_tokens: int) -> Completion:
        if not self.api_key:
            raise ProviderError("no provider API key configured (GROQ_API_KEY)", fatal=True)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "required",
            "max_completion_tokens": max_tokens,
            "temperature": 0,
        }
        if "gpt-oss" in self.model:
            body["reasoning_effort"] = "low"
        try:
            resp = self.http.post(f"{self.base_url}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.TransportError as exc:
            raise ProviderError(f"transport: {exc}", retry_after=5)
        headers = {k.lower(): v for k, v in resp.headers.items()}
        if resp.status_code == 429:
            raise ProviderError("rate limited", retry_after=_retry_after(headers))
        if resp.status_code >= 500:
            raise ProviderError(f"provider {resp.status_code}", retry_after=10)
        if resp.status_code >= 400:
            raise ProviderError(f"provider rejected the request: {resp.status_code} {resp.text[:200]}", fatal=True)
        data = resp.json()
        usage = data.get("usage") or {}
        return Completion(data["choices"][0]["message"], int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)), headers)


def _retry_after(headers: dict[str, str]) -> float:
    for key in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        value = headers.get(key)
        if value:
            return parse_duration(value)
    return 10.0


def parse_duration(value: str) -> float:
    """Parse Retry-After seconds or Groq-style durations like '2m59.56s' or '7.66s'."""
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    total, num = 0.0, ""
    units = {"h": 3600.0, "m": 60.0, "s": 1.0}
    i = 0
    while i < len(value):
        ch = value[i]
        if ch.isdigit() or ch == ".":
            num += ch
        elif value[i : i + 2] == "ms":
            total += float(num or 0) / 1000
            num = ""
            i += 1
        elif ch in units:
            total += float(num or 0) * units[ch]
            num = ""
        i += 1
    return total or 1.0


class ScriptedProvider:
    """Deterministic provider for tests and demos: replays tool calls."""

    def __init__(self, calls: list[tuple[str, dict[str, Any]]], name: str = "scripted", model: str = "scripted-1", tokens: int = 500, headers: dict[str, str] | None = None) -> None:
        self.name = name
        self.model = model
        self.calls = list(calls)
        self.tokens = tokens
        self.headers = headers or {}
        self.i = 0

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_tokens: int) -> Completion:
        import json

        tool, args = self.calls[min(self.i, len(self.calls) - 1)]
        self.i += 1
        msg = {"role": "assistant", "content": None, "tool_calls": [{"id": f"call_{self.i}", "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]}
        return Completion(msg, self.tokens, 20, self.headers)
