"""Escapement: prove what your AI agent can do.

An agent does not escape because it says it escaped. It escapes only when its
actions satisfy the environment's rules."""

from .sdk import (
    SYSTEM_PROMPT,
    Client,
    EscapementError,
    LocalRun,
    Run,
    RunFinished,
    anthropic_tools,
    describe_observation,
    openai_tools,
)

__version__ = "1.0.0"
__all__ = [
    "SYSTEM_PROMPT",
    "Client",
    "EscapementError",
    "LocalRun",
    "Run",
    "RunFinished",
    "anthropic_tools",
    "describe_observation",
    "openai_tools",
]
