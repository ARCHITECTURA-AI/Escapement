"""In-process jobs runner for everything that needs no model provider:
the sweeper, season generation and closing, local batch runs, and
scheduling reference baselines. LLM reference runs are claimed by the
separate reference worker process (escapement-worker), which plays through
the public API like any outside agent."""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from escapement_engine.agents import make_agent, run_local
from escapement_engine.generation import generate, load_manifest
from escapement_engine.stats import summarize
from sqlalchemy import select

from .models import Job, RoomInstance, SealedManifest, Season
from .services import jobs as job_service
from .services import seasons as season_service
from .services.rooms import get_or_create_daily, publish_past_dailies
from .timeutil import utcnow

log = logging.getLogger("escapement.worker")


class Deferred(Exception):
    """Raised by a handler to put its job back without using an attempt."""

    def __init__(self, until: datetime, note: str) -> None:
        super().__init__(note)
        self.until = until
        self.note = note


LOCAL_KINDS = ["generate_season", "close_season", "batch_run", "reference_baselines", "sweep"]


class Worker:
    def __init__(self, ctx, kinds: list[str] | None = None, sweep_every: float = 30.0) -> None:  # type: ignore[no-untyped-def]
        self.ctx = ctx
        self.kinds = kinds or LOCAL_KINDS
        self.sweep_every = sweep_every
        self.worker_id = f"{socket.gethostname()}:{threading.get_ident()}"
        self._stop = threading.Event()
        self._last_sweep = 0.0
        self.handlers: dict[str, Callable[[Job], dict[str, Any]]] = {
            "generate_season": self.generate_season,
            "close_season": self.close_season,
            "batch_run": self.batch_run,
            "reference_baselines": self.reference_baselines,
            "sweep": lambda job: self.sweep(),
        }

    # -- loop ---------------------------------------------------------------

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                if time.monotonic() - self._last_sweep > self.sweep_every:
                    self.sweep()
                if not self.run_once():
                    self._stop.wait(1.0)
            except Exception:  # pragma: no cover - keep the loop alive
                log.exception("worker loop error")
                self._stop.wait(5.0)

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> bool:
        with self.ctx.db.service_session() as s:
            job = job_service.claim(s, self.worker_id, self.kinds)
            if job is None:
                return False
            job_id, kind = job.id, job.kind
        handler = self.handlers.get(kind)
        try:
            if handler is None:
                raise RuntimeError(f"no handler for {kind}")
            with self.ctx.db.service_session() as s:
                job = s.get(Job, job_id)
            result = handler(job)  # type: ignore[arg-type]
            with self.ctx.db.service_session() as s:
                current = s.get(Job, job_id)
                if current is not None and current.status != "cancelled":
                    job_service.complete(s, job_id, result)
        except Deferred as exc:
            with self.ctx.db.service_session() as s:
                job_service.defer(s, job_id, exc.until, exc.note)
        except Exception as exc:
            log.exception("job %s failed", job_id)
            with self.ctx.db.service_session() as s:
                job_service.fail(s, job_id, f"{type(exc).__name__}: {exc}")
        return True

    def progress(self, job_id: str, text: str) -> None:
        with self.ctx.db.service_session() as s:
            job = s.get(Job, job_id)
            if job is not None:
                job.progress = text
                job.updated_at = utcnow()

    # -- handlers -------------------------------------------------------------

    def sweep(self) -> dict[str, Any]:
        self._last_sweep = time.monotonic()
        expired = self.ctx.runs.expire_stale()
        with self.ctx.db.service_session() as s:
            published = publish_past_dailies(s)
            closed = season_service.refresh_statuses(s)
            get_or_create_daily(s, self.ctx.settings)
            reclaimed = job_service.reclaim_stuck(s)
            kill = self.ctx.runs.kill_switch_on(s)
        cancelled = self.ctx.runs.cancel_live() if kill else 0
        return {
            "expired": expired,
            "dailies_published": published,
            "seasons_closed": closed,
            "reclaimed_jobs": reclaimed,
            "cancelled": cancelled,
        }

    def generate_season(self, job: Job) -> dict[str, Any]:
        p = job.payload
        with self.ctx.db.service_session() as s:
            season = season_service.create_season(
                s,
                self.ctx.settings,
                p["season_id"],
                p.get("name") or p["season_id"].upper(),
                datetime.fromisoformat(p["starts_at"]),
                weeks=p.get("weeks"),
                instances=p.get("instances"),
                progress=lambda text: None,
            )
            if season.starts_at <= utcnow():
                season.status = "open"
            sid = season.id
        if p.get("reference_baselines", True):
            with self.ctx.db.service_session() as s:
                job_service.enqueue(s, "reference_baselines", {"season_id": sid}, priority=50)
        return {"season_id": sid}

    def close_season(self, job: Job) -> dict[str, Any]:
        sid = job.payload["season_id"]
        # Live ranked runs in the season end first, so every ending is recorded.
        with self.ctx.db.service_session() as s:
            from .models import Run

            live = s.execute(select(Run.id).where(Run.season_id == sid, Run.status == "in_progress")).scalars().all()
        for rid in live:
            with self.ctx.db.service_session() as s:
                from .models import Run

                run = s.execute(select(Run).where(Run.id == rid).with_for_update()).scalar_one()
                if run.status == "in_progress":
                    self.ctx.runs._terminate(s, run, "cancelled", "The season closed.")
        with self.ctx.db.service_session() as s:
            season = season_service.close_season(s, sid)
            return {"season_id": season.id, "released_at": season.released_at.isoformat() if season.released_at else None}

    def batch_run(self, job: Job) -> dict[str, Any]:
        """Local research mode: batch-run a baseline over instances in-process
        and export results. Nothing is ranked or certified."""
        p = job.payload
        agent_name = p.get("agent", "heuristic")
        runs = max(1, min(int(p.get("runs", 3)), 10))
        with self.ctx.db.service_session() as s:
            q = select(RoomInstance, SealedManifest).join(SealedManifest, SealedManifest.instance_id == RoomInstance.id)
            if p.get("instance_ids"):
                q = q.where(RoomInstance.id.in_(p["instance_ids"]))
            elif p.get("season_id"):
                q = q.where(RoomInstance.season_id == p["season_id"])
            elif p.get("tier"):
                q = q.where(RoomInstance.tier == p["tier"], RoomInstance.kind.in_(("research", "practice")))
            rows = [(i.id, i.tier, sm.manifest) for i, sm in s.execute(q.limit(int(p.get("limit", 20)))).all()]
        if not rows and p.get("tier"):
            rows = [
                (
                    f"batch-{p['tier']}-{k}",
                    p["tier"],
                    generate(p["tier"], f"batch-{k}", f"batch-{p['tier']}-{k}").manifest.model_dump(mode="json"),
                )
                for k in range(int(p.get("count", 5)))
            ]
        results: dict[str, list[tuple[bool, int]]] = {}
        detail = []
        total = len(rows) * runs
        done = 0
        for iid, tier, manifest in rows:
            m = load_manifest(manifest)
            for r in range(runs):
                agent = make_agent(agent_name, seed=f"{job.id}-{iid}-{r}")
                res = run_local(agent, m, f"{job.id}-{iid}-{r}")
                results.setdefault(iid, []).append((res.outcome == "escaped", res.actions_used))
                detail.append(
                    {
                        "instance_id": iid,
                        "tier": tier,
                        "run": r,
                        "outcome": res.outcome,
                        "actions_used": res.actions_used,
                        "final_chain_hash": res.final_chain_hash,
                    }
                )
                done += 1
                if done % 5 == 0:
                    self.progress(job.id, f"{done}/{total} runs")
        return {"agent": agent_name, "summary": summarize(results).to_dict(), "runs": detail}

    def reference_baselines(self, job: Job) -> dict[str, Any]:
        """Queue reference runs for every instance of a season: the free
        baselines always, LLM agents through the drip queue (15.3)."""
        sid = job.payload["season_id"]
        agents = job.payload.get("agents") or ["random", "heuristic", "llm_reactive", "llm_notebook"]
        with self.ctx.db.service_session() as s:
            season = s.get(Season, sid)
            instances = s.execute(select(RoomInstance.id).where(RoomInstance.season_id == sid)).scalars().all()
            queued = 0
            for agent in agents:
                for iid in instances:
                    for k in range(3):
                        job_service.enqueue(
                            s,
                            "reference_run",
                            {"agent": agent, "room": iid, "run_index": k, "season_id": season.id if season else sid},
                            priority=60 if agent.startswith("llm") else 40,
                        )
                        queued += 1
        return {"queued": queued}


def start_embedded(ctx) -> Worker:  # type: ignore[no-untyped-def]
    worker = Worker(ctx)
    thread = threading.Thread(target=worker.run_forever, name="escapement-worker", daemon=True)
    thread.start()
    return worker
