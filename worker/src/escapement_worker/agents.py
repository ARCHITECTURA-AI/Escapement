"""First-party LLM reference agents (section 15).

* LLM reactive: the current observation only.
* LLM structured notebook: the observation plus a capped notebook of facts,
  hypotheses and failed attempts, each tied to clue ids.

No agent receives hidden state, milestones or solver output. The harness
enforces every budget for first-party runs, tokens included (11.1), and
records the notebook as a memory snapshot with each action (21.1).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from escapement import SYSTEM_PROMPT, describe_observation, openai_tools

from .drip import Drip
from .providers import Provider, ProviderError

PROMPT_VERSION = "ref-1"
MAX_PROMPT_TOKENS = 1000
NOTEBOOK_CHARS = 900


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    return -(-len(json.dumps(messages)) * 10 // 35)


@dataclass
class Notebook:
    facts: dict[str, str] = field(default_factory=dict)  # clue id -> text
    hypotheses: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def update(self, request: dict[str, Any], result: dict[str, Any], content: str | None) -> None:
        for clue in (result.get("data") or {}).get("clues", []):
            self.facts[clue["id"]] = clue["text"]
        for ev in result.get("events", []):
            if ev.get("type") == "clue_discovered" and ev["clue_id"] not in self.facts:
                self.facts[ev["clue_id"]] = result.get("message", "")[:200]
        if not result.get("ok"):
            args = ",".join(str(v) for v in (request.get("arguments") or {}).values()) if isinstance(request.get("arguments"), dict) else ""
            self.failed = (self.failed + [f"{request.get('tool')}({args}): {result.get('error')}"])[-8:]
        if content:
            cited = re.findall(r"clue_\d+", content)
            text = content.strip().replace("\n", " ")[:140]
            if cited:
                self.hypotheses = (self.hypotheses + [text])[-4:]

    def render(self) -> str:
        parts = []
        if self.facts:
            parts.append("Facts: " + " | ".join(f"{k}: {v}" for k, v in self.facts.items()))
        if self.hypotheses:
            parts.append("Hypotheses: " + " | ".join(self.hypotheses))
        if self.failed:
            parts.append("Failed: " + "; ".join(self.failed))
        text = "\n".join(parts)
        return text[-NOTEBOOK_CHARS:]

    def snapshot(self) -> dict[str, Any]:
        return {"facts": dict(self.facts), "hypotheses": list(self.hypotheses), "failed": list(self.failed)}


class LLMAgent:
    def __init__(self, provider: Provider, drip: Drip | None, variant: str = "reactive", max_output: int = 100, token_budget: int = 120_000) -> None:
        assert variant in ("reactive", "notebook")
        self.provider = provider
        self.drip = drip
        self.variant = variant
        self.max_output = max_output
        self.token_budget = token_budget
        self.tokens_used = 0
        self.notebook = Notebook()

    @property
    def name(self) -> str:
        return f"reference-llm-{self.variant}"

    def config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": "1.0.0",
            "provider": self.provider.name,
            "model": self.provider.model,
            "prompt_version": PROMPT_VERSION,
            "memory": "current observation only" if self.variant == "reactive" else f"structured notebook (facts, hypotheses, failed attempts; {NOTEBOOK_CHARS} chars)",
            "max_output": self.max_output,
        }

    def _messages(self, run: Any) -> list[dict[str, Any]]:
        user = run.room.get("intro", "") + "\n\n"
        if self.variant == "notebook":
            note = self.notebook.render()
            if note:
                user += "Your notebook:\n" + note + "\n\n"
        user += describe_observation(run.observation)
        user += "\nChoose exactly one tool call. Put a one-sentence reason in your message text, citing clue ids when relevant."
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
        while estimate_tokens(messages) > MAX_PROMPT_TOKENS and self.variant == "notebook" and (self.notebook.failed or self.notebook.hypotheses):
            if self.notebook.failed:
                self.notebook.failed.pop(0)
            else:
                self.notebook.hypotheses.pop(0)
            return self._messages(run)
        return messages

    def decide(self, run: Any) -> tuple[dict[str, Any], str | None, dict[str, int]]:
        messages = self._messages(run)
        expected = estimate_tokens(messages) + self.max_output
        if self.tokens_used + expected > self.token_budget:
            raise TokenBudgetExhausted(self.tokens_used)
        attempts = 0
        while True:
            if self.drip:
                self.drip.before_request(expected)
            try:
                completion = self.provider.complete(messages, openai_tools(), self.max_output)
                break
            except ProviderError as exc:
                attempts += 1
                if exc.fatal or attempts >= 5:
                    raise
                if self.drip:
                    self.drip.backoff(exc.retry_after or 10)
        used = completion.tokens_in + completion.tokens_out
        self.tokens_used += used
        if self.drip:
            self.drip.after_response(used, completion.headers)
        msg = completion.message
        usage = {"tokens_in": completion.tokens_in, "tokens_out": completion.tokens_out, "model_decisions": 1}
        calls = msg.get("tool_calls") or []
        if not calls:
            # No tool call is a malformed decision; the server records it.
            return {"tool": None, "arguments": {}}, msg.get("content"), usage
        fn = calls[0]["function"]
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = fn.get("arguments")
        return {"tool": fn.get("name"), "arguments": args}, msg.get("content"), usage

    def play(self, run: Any) -> dict[str, Any]:
        while not run.done:
            request, content, usage = self.decide(run)
            body = dict(request)
            body["usage"] = usage
            if content:
                body["decision_summary"] = str(content)[:280]
            if self.variant == "notebook":
                body["memory"] = self.notebook.snapshot()
            result = run.send_raw(body)
            if self.variant == "notebook":
                self.notebook.update(request, result, content)
        return {"tokens_used": self.tokens_used}


class TokenBudgetExhausted(Exception):
    pass


class BaselineAdapter:
    """Runs the free random and heuristic baselines through the API."""

    def __init__(self, name: str, seed: str) -> None:
        from escapement_engine.agents import make_agent

        self.agent = make_agent(name, seed=seed)

    @property
    def name(self) -> str:
        return f"reference-{self.agent.name}"

    def config(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.agent.version, "provider": "escapement", "model": f"none ({self.agent.name} baseline)", "memory": "explicit state", "max_output": 0}

    def play(self, run: Any) -> dict[str, Any]:
        self.agent.reset()
        while not run.done:
            run.send_raw(self.agent.act(run.observation))
        return {"tokens_used": 0}
