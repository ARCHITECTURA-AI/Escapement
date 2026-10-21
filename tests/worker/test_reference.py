"""Reference worker (section 15) and the drip queue (15.3)."""

from __future__ import annotations

from datetime import UTC

import pytest
from escapement import Client
from escapement_api.models import ApiKey, Job, Setting, User, UserPrivate
from escapement_api.security import new_api_key
from escapement_api.services import jobs as job_service
from escapement_engine.generation import build_practice
from escapement_worker.drip import DailyLimitReached, Drip, Limits
from escapement_worker.main import ReferenceWorker
from escapement_worker.providers import ScriptedProvider, parse_duration

from ..api.conftest import app, settings
from ..client.test_sdk import AppTransport


def no_sleep_drip(ctx):
    return lambda provider, model: Drip(ctx.db, provider, model, sleep=lambda seconds: None)


def reference_client(app) -> Client:
    ctx = app.state.ctx
    with ctx.db.owner_session() as s:
        user = User(handle="escapement-reference", is_system=True, profile_public=True)
        s.add(user)
        s.flush()
        s.add(UserPrivate(user_id=user.id))
        key, prefix, digest = new_api_key()
        s.add(ApiKey(user_id=user.id, name="ref", prefix=prefix, key_hash=digest))
    return Client(api_key=key, base_url="http://testserver", transport=AppTransport(app))


def solution_calls():
    return [(a["tool"], a["arguments"]) for a in build_practice().solution]


def test_llm_reference_run_is_attested_and_cached(app):
    ctx = app.state.ctx
    client = reference_client(app)
    worker = ReferenceWorker(
        ctx,
        client,
        provider_factory=lambda model: ScriptedProvider(solution_calls(), name="groq", model=model),
        models=["openai/gpt-oss-20b"],
        drip_factory=no_sleep_drip(ctx),
    )
    with ctx.db.service_session() as s:
        job_service.enqueue(s, "reference_run", {"agent": "llm_notebook", "room": "practice", "run_index": 0})
    assert worker.run_once()
    with ctx.db.service_session() as s:
        job = s.query(Job).one()
        assert job.status == "done", job.error
        result = job.result["results"][0]
    assert result["status"] == "escaped"
    run = client.request("GET", f"/api/v1/runs/{result['run_id']}")
    cert = client.request("GET", f"/api/v1/certificates/{run['certificate_id']}")["certificate"]
    assert cert["agent"]["model_attested"] is True and cert["agent"]["provider"] == "groq"
    assert cert["agent"]["model"] == "openai/gpt-oss-20b" and cert["self_reported_fields"] == []
    replay = client.request("GET", f"/api/v1/runs/{result['run_id']}/replay")["replay"]
    assert replay["mode"] == "reference" and replay["steps"][0]["usage"]["tokens_in"] == 500
    # Cached: the same instance, configuration and seed never rerun.
    with ctx.db.service_session() as s:
        job_service.enqueue(s, "reference_run", {"agent": "llm_notebook", "room": "practice", "run_index": 0})
    assert worker.run_once()
    with ctx.db.service_session() as s:
        second = [j for j in s.query(Job).all() if j.result and j.result["results"][0].get("cached")]
        assert len(second) == 1
    # The tokens were counted against today's provider budget.
    usage = worker.drips["openai/gpt-oss-20b"].usage_today()
    assert usage["requests"] == len(solution_calls()) and usage["tokens"] == 520 * len(solution_calls())


def test_baselines_run_through_api(app):
    ctx = app.state.ctx
    client = reference_client(app)
    worker = ReferenceWorker(ctx, client, models=["x"])
    with ctx.db.service_session() as s:
        job_service.enqueue(s, "reference_run", {"agent": "heuristic", "room": "practice", "run_index": 0})
    worker.run_once()
    with ctx.db.service_session() as s:
        job = s.query(Job).one()
        assert job.status == "done", job.error
        assert job.result["results"][0]["status"] == "escaped"
    ref = client.request("GET", "/api/v1/reference")
    assert ref["practice"][0]["runs"] == 1


def test_drip_stops_at_ninety_percent(app):
    ctx = app.state.ctx
    slept = []
    drip = Drip(ctx.db, "groq", "m", Limits(tokens_per_day=10_000), sleep=slept.append)
    drip.before_request(1000)
    drip.after_response(8500, {})
    with pytest.raises(DailyLimitReached):
        drip.before_request(1000)


def test_drip_spaces_requests_and_reads_headers(app):
    ctx = app.state.ctx
    slept = []
    drip = Drip(ctx.db, "groq", "m2", Limits(requests_per_minute=30), sleep=slept.append)
    drip.before_request(100)
    drip.after_response(100, {})
    drip.before_request(100)
    assert slept and 1.5 < slept[-1] <= 2.0  # 60 / 30 rpm: never bursts
    drip.after_response(100, {"x-ratelimit-remaining-tokens": "10", "x-ratelimit-reset-tokens": "7.5s"})
    drip.before_request(100)
    assert slept[-1] >= 7.0


def test_daily_limit_defers_job(app):
    ctx = app.state.ctx
    client = reference_client(app)
    worker = ReferenceWorker(
        ctx,
        client,
        provider_factory=lambda model: ScriptedProvider(solution_calls(), model=model),
        models=["m3"],
        drip_factory=no_sleep_drip(ctx),
    )
    with ctx.db.owner_session() as s:
        from datetime import datetime, timezone

        s.add(Setting(key=f"reference_usage:scripted:m3:{datetime.now(UTC).date().isoformat()}", value={"tokens": 195_000, "requests": 10}))
        job_service.enqueue(s, "reference_run", {"agent": "llm_reactive", "room": "practice", "run_index": 0})
    worker.run_once()
    with ctx.db.service_session() as s:
        job = s.query(Job).one()
        assert job.status == "queued" and "daily budget" in (job.progress or "")


def test_parse_duration():
    assert parse_duration("2m59.56s") == pytest.approx(179.56)
    assert parse_duration("7.66s") == pytest.approx(7.66)
    assert parse_duration("12") == 12.0
    assert parse_duration("250ms") == pytest.approx(0.25)
