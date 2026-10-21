"""escapement-worker: claims reference_run jobs and plays them through the
public API with the reference user's API key.

    ESCAPEMENT_DATABASE_URL=...            jobs table and usage counters
    ESCAPEMENT_BASE_URL=http://api:8000    the public API
    ESCAPEMENT_REFERENCE_KEY=esk_...       from `escapement-api ops reference-key`
    GROQ_API_KEY=gsk_...                   provider key for LLM reference agents
    REFERENCE_MODELS=openai/gpt-oss-20b,openai/gpt-oss-120b
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from escapement import Client
from escapement.sdk.errors import EscapementError
from escapement_api.app import build_context
from escapement_api.canonical_hash import config_hash
from escapement_api.models import Job, ReferenceCache
from escapement_api.worker import Deferred, Worker

from .agents import BaselineAdapter, LLMAgent, TokenBudgetExhausted
from .drip import DailyLimitReached, Drip
from .providers import OpenAICompatible, ProviderError

log = logging.getLogger("escapement.reference")


class ReferenceWorker(Worker):
    def __init__(self, ctx, client: Client, provider_factory=None, models: list[str] | None = None, drip_factory=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(ctx, kinds=["reference_run"])
        self.sweep_every = float("inf")  # the API's own worker sweeps
        self.client = client
        self.models = models or [m.strip() for m in os.environ.get("REFERENCE_MODELS", "openai/gpt-oss-20b").split(",") if m.strip()]
        self.provider_factory = provider_factory or (lambda model: OpenAICompatible(model=model))
        self.drips: dict[str, Drip] = {}
        self.drip_factory = drip_factory or (lambda provider, model: Drip(self.ctx.db, provider, model))
        self.handlers["reference_run"] = self.reference_run

    def _agents(self, kind: str, seed: str) -> list[Any]:
        if kind in ("random", "heuristic"):
            return [BaselineAdapter(kind, seed)]
        variant = {"llm_reactive": "reactive", "llm_notebook": "notebook"}[kind]
        out = []
        for model in self.models:
            provider = self.provider_factory(model)
            if getattr(provider, "api_key", "configured") is None:
                log.warning("no provider key: skipping %s for %s", kind, model)
                continue
            if model not in self.drips:
                self.drips[model] = self.drip_factory(provider.name, model)
            drip = self.drips[model]
            out.append(LLMAgent(provider, drip, variant=variant, max_output=int(os.environ.get("REFERENCE_MAX_OUTPUT", "100"))))
        return out

    def reference_run(self, job: Job) -> dict[str, Any]:
        p = job.payload
        room = p["room"]
        seed = f"{p.get('run_index', 0)}"
        meta = self.client.request("GET", f"/api/v1/rooms/{room}")
        results = []
        for agent in self._agents(p["agent"], seed=f"{meta['instance_hash'][:12]}-{seed}"):
            cfg = agent.config()
            key = f"{meta['instance_hash']}:{config_hash(cfg)}:{seed}"
            with self.ctx.db.service_session() as s:
                cached = s.get(ReferenceCache, key)
                if cached is not None:
                    results.append({"agent": cfg["name"], "model": cfg["model"], "cached": True, "run_id": cached.run_id})
                    continue
            if isinstance(agent, LLMAgent) and agent.drip is not None:
                try:
                    agent.drip.before_request(30_000)  # do not start a run the day's budget cannot finish
                except DailyLimitReached as exc:
                    raise Deferred(exc.resume_at, "provider daily budget reached; resumes after 00:00 UTC")
            try:
                run = self.client.create_run(
                    room,
                    agent={
                        "name": cfg["name"],
                        "version": cfg["version"],
                        "model": cfg["model"],
                        "framework": f"escapement reference harness {cfg.get('prompt_version', '')}".strip(),
                        "memory": cfg["memory"],
                        "config_hash": config_hash(cfg),
                    },
                    provider=cfg["provider"],
                    reference_seed=seed,
                    replace_active=True,
                )
            except EscapementError as exc:
                if exc.code in ("SEASON_NOT_OPEN", "RUN_LIMIT"):
                    results.append({"agent": cfg["name"], "skipped": exc.code})
                    continue
                raise
            outcome: dict[str, Any] = {"agent": cfg["name"], "model": cfg["model"], "run_id": run.id}
            try:
                outcome.update(agent.play(run))
                run.finish()
            except TokenBudgetExhausted:
                run.finish()
            except (ProviderError, DailyLimitReached) as exc:
                run.client.request("POST", f"/api/v1/runs/{run.id}/finish", token=run.token, json={"reason": "reference_provider_failure"})
                if isinstance(exc, DailyLimitReached):
                    raise Deferred(exc.resume_at, "provider daily budget reached; resumes after 00:00 UTC")
                raise
            outcome["status"] = run.status
            if run.status not in ("cancelled", "engine_error", "reference_provider_failure"):
                with self.ctx.db.service_session() as s:
                    s.add(ReferenceCache(key=key, run_id=run.id))
            results.append(outcome)
        return {"results": results}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="escapement-worker")
    parser.add_argument("--once", action="store_true", help="Process one job and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    ctx = build_context()
    key = os.environ.get("ESCAPEMENT_REFERENCE_KEY")
    if not key:
        raise SystemExit("Set ESCAPEMENT_REFERENCE_KEY (create one with `escapement-api ops reference-key`).")
    client = Client(api_key=key, base_url=os.environ.get("ESCAPEMENT_BASE_URL", "http://localhost:8000"))
    worker = ReferenceWorker(ctx, client)
    if args.once:
        worker.run_once()
    else:
        log.info("reference worker started; models: %s", ", ".join(worker.models))
        worker.run_forever()


if __name__ == "__main__":
    main()
