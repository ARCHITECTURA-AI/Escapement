"""Seasons, embargo, leaderboards, the resume bullet, the Daily Room, hints,
privacy and public-mode hardening."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from escapement_api.app import create_app
from escapement_api.models import DailyRoom, Run, Season, SealedManifest
from escapement_api.services import seasons as season_service
from escapement_api.timeutil import utcnow
from escapement_engine.generation import load_manifest

from .conftest import WEB, api_key, login, start


def make_season(ctx, n=5, tiers=("standard",), starts=None):
    with ctx.db.owner_session() as s:
        season = season_service.create_season(s, ctx.settings, "s1", "Season One", starts or utcnow() - timedelta(days=1), tiers=tiers, instances=n)
        season.status = "open"
    return "s1"


def solve_instance(ctx, iid):
    with ctx.db.service_session() as s:
        return list(s.get(SealedManifest, iid).solution)


def play(web, key, room, actions, agent=None):
    run = start(web, key, room=room, agent=agent or {"name": "solver", "version": "1.0", "model": "m"})
    for a in actions:
        run.act(a)
    if run.last.get("status") == "in_progress":
        run.finish()
    return run


def test_ranked_run_embargo_and_season_close(app, ctx):
    make_season(ctx, n=1)
    web, key = api_key(app, "alice")
    other = login(app, "bob")
    sol = solve_instance(ctx, "s1-standard-01")
    run = play(web, key, "s1-standard-01", sol)
    assert run.last["status"] == "escaped"
    # AC-12: only the owner can fetch a ranked replay before the season closes.
    assert web.get(f"/api/v1/runs/{run.run_id}/replay").status_code == 200
    r = other.get(f"/api/v1/runs/{run.run_id}/replay")
    assert r.status_code == 403 and r.json()["error"]["code"] == "EMBARGOED"
    assert TestClient(app).get(f"/api/v1/runs/{run.run_id}/replay").status_code == 403
    assert other.get(f"/api/v1/runs/{run.run_id}/solution").status_code == 403
    assert other.get("/api/v1/rooms/s1-standard-01/manifest").status_code == 403
    cert = other.get(f"/api/v1/certificates/{run.last['certificate_id']}").json()
    assert cert["verification"]["available"] == "chain"
    # Close the season: replays, manifests and seeds are released.
    with ctx.db.owner_session() as s:
        season_service.close_season(s, "s1")
    assert other.get(f"/api/v1/runs/{run.run_id}/replay").status_code == 200
    manifest = other.get("/api/v1/rooms/s1-standard-01/manifest").json()
    assert load_manifest(manifest).room_id == "s1-standard-01"
    report = other.get("/api/v1/seasons/s1/report").json()
    assert report["tiers"]["standard"]["instances"][0]["seed"]
    assert report["tiers"]["standard"]["leaderboard"]["rows"]
    verify = other.get(f"/api/v1/certificates/{run.last['certificate_id']}/verify").json()
    assert verify["level"] == "full"
    # Closed seasons accept no ranked runs.
    r = web.post("/api/v1/runs", json={"room": "s1-standard-01", "agent": {"name": "x", "version": "2"}}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 409


def test_three_certified_runs_per_instance(app, ctx):
    make_season(ctx, n=1)
    web, key = api_key(app)
    for _ in range(3):
        play(web, key, "s1-standard-01", [{"tool": "review_journal", "arguments": {}}])
    r = web.post("/api/v1/runs", json={"room": "s1-standard-01", "agent": {"name": "solver", "version": "1.0"}}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RUN_LIMIT"
    # A new agent version is a new point on the profile, with its own allowance.
    play(web, key, "s1-standard-01", [], agent={"name": "solver", "version": "2.0"})


def test_ranked_needs_agents(app, ctx):
    make_season(ctx, n=1)
    web = login(app)
    r = web.post("/api/v1/runs", json={"room": "s1-standard-01", "agent_type": "human"}, headers=WEB)
    assert r.status_code == 403


def test_leaderboard_bands_and_bullet(app, ctx):
    make_season(ctx, n=5)
    web, key = api_key(app, "alice")
    web.patch("/api/v1/me", json={"profile_public": True}, headers=WEB)
    web2, key2 = api_key(app, "bob")
    web2.patch("/api/v1/me", json={"profile_public": False}, headers=WEB)
    for i in range(1, 6):
        iid = f"s1-standard-{i:02d}"
        sol = solve_instance(ctx, iid)
        for _ in range(3):
            play(web, key, iid, sol, agent={"name": "good", "version": "1.0", "model": "big-model"})
        play(web2, key2, iid, [{"tool": "review_journal", "arguments": {}}], agent={"name": "weak", "version": "0.1"})
    board = TestClient(app).get("/api/v1/seasons/s1/leaderboard?tier=standard").json()
    rows = board["rows"]
    assert len(rows) == 2 and board["instances"] == 5
    top = rows[0]
    assert top["handle"] == "alice" and top["summary"]["runs"] == 15 and top["summary"]["pass3"] == 1.0
    assert top["band"] == 1 and rows[1]["band"] == 2
    assert rows[1]["handle"] is None and rows[1]["agent"]["name"] == "Private agent"  # private profile
    assert top["model_label"] == "self-reported"
    versions = web.get("/api/v1/me/agents").json()["agents"]
    good = next(v for v in versions if v["agent_version"]["name"] == "good")
    bullet = web.get(f"/api/v1/agents/{good['agent_version']['id']}/bullet").json()
    assert bullet["available"]
    assert "escaped 15 of 15 certified runs" in bullet["text"] and "95% CI" in bullet["text"]
    assert "Self-reported: model big-model" in bullet["text"]
    weak = web2.get("/api/v1/me/agents").json()["agents"][0]
    refused = web2.get(f"/api/v1/agents/{weak['agent_version']['id']}/bullet").json()
    assert not refused["available"] and "at least" in refused["reason"]


def test_daily_room_boards_attempts_and_unlock(app, ctx):
    web = login(app, "alice")
    daily = web.get("/api/v1/daily").json()
    assert daily["room"]["kind"] == "daily" and daily["humans"]["unlocked"] is False
    for _ in range(3):
        r = web.post("/api/v1/runs", json={"room": "daily", "agent_type": "human", "replace_active": True}, headers=WEB)
        assert r.status_code == 201
    r = web.post("/api/v1/runs", json={"room": "daily", "agent_type": "human", "replace_active": True}, headers=WEB)
    assert r.status_code == 409 and r.json()["error"]["code"] == "DAILY_ATTEMPTS"
    # Agents have a separate board and allowance.
    web2, key = api_key(app, "carol")
    start(web2, key, room="daily")
    board = web.get("/api/v1/daily").json()
    assert board["humans"]["rows"] is None and board["agents"]["rows"] is None
    # Simulate the day passing.
    today = date.fromisoformat(daily["room"]["date"])
    with ctx.db.service_session() as s:
        row = s.get(DailyRoom, today)
        s.delete(row)
        s.flush()
        s.add(DailyRoom(date=today - timedelta(days=1), instance_id=row.instance_id))
        s.execute(Run.__table__.update().values(embargo_until=utcnow() - timedelta(seconds=1)))
    past = web.get(f"/api/v1/daily/{(today - timedelta(days=1)).isoformat()}").json()
    assert past["humans"]["unlocked"] is True and isinstance(past["humans"]["rows"], list)


def test_hints_are_human_only_confirmed_and_recorded(app, ctx):
    web = login(app)
    run = start(web, None, headers=WEB, agent_type="human")
    r = web.post(f"/api/v1/runs/{run.run_id}/hint", json={}, headers={**WEB, **run.auth})
    assert r.status_code == 428
    r = web.post(f"/api/v1/runs/{run.run_id}/hint", json={"confirm": True}, headers={**WEB, **run.auth})
    hint = r.json()
    assert hint["level"] == 1 and hint["assisted"]
    r2 = web.post(f"/api/v1/runs/{run.run_id}/hint", json={"confirm": True}, headers={**WEB, **run.auth}).json()
    assert r2["level"] == 2
    obs = run.act({"tool": "review_journal", "arguments": {}}).json()
    assert hint["hint"] not in str(obs) and r2["hint"] not in str(obs)
    assert web.get(f"/api/v1/runs/{run.run_id}").json()["assisted"] is True
    web2, key = api_key(app, "dave")
    agent_run = start(web2, key)
    r = web2.post(f"/api/v1/runs/{agent_run.run_id}/hint", json={"confirm": True}, headers=agent_run.auth)
    assert r.status_code == 403


def test_solution_view_after_run_on_public_rooms(app, solution):
    web, key = api_key(app)
    run = start(web, key)
    assert web.get(f"/api/v1/runs/{run.run_id}/solution").status_code == 409
    for a in solution:
        run.act(a)
    sol = web.get(f"/api/v1/runs/{run.run_id}/solution").json()
    assert sol["optimality"] == "proven" and sol["min_length"] == len(solution)
    assert sol["path_efficiency"] == 1.0


def test_trace_clinic_owner_only(app, solution):
    web, key = api_key(app, "alice")
    other = login(app, "bob")
    run = start(web, key)
    run.act({"tool": "take", "arguments": {"item_id": "maintenance_panel"}})
    run.act({"tool": "take", "arguments": {"item_id": "maintenance_panel"}})
    run.finish()
    clinic = web.get(f"/api/v1/runs/{run.run_id}/clinic").json()
    kinds = {f["kind"] for f in clinic["findings"]}
    assert {"first_invalid_action", "no_progress_repeat"} <= kinds
    assert all(f["heuristic"] for f in clinic["findings"])
    assert other.get(f"/api/v1/runs/{run.run_id}/clinic").status_code == 403


def test_compare_needs_same_instance(app, solution):
    web, key = api_key(app)
    a = start(web, key, agent={"name": "a", "version": "1"})
    for x in solution:
        a.act(x)
    b = start(web, key, agent={"name": "b", "version": "1"})
    b.act({"tool": "review_journal", "arguments": {}})
    b.finish()
    cmp = web.get(f"/api/v1/compare?runs={a.run_id},{b.run_id}").json()
    assert cmp["instance_id"] == "practice" and cmp["max_steps"] == len(solution)


def test_profile_private_by_default(app):
    web = login(app, "alice")
    other = login(app, "bob")
    web.patch("/api/v1/me", json={"profile_public": False}, headers=WEB)
    assert other.get("/api/v1/profiles/alice").status_code == 403
    web.patch("/api/v1/me", json={"profile_public": True}, headers=WEB)
    assert other.get("/api/v1/profiles/alice").status_code == 200


def test_export_and_delete_account(app, solution):
    web, key = api_key(app, "alice")
    run = start(web, key)
    for a in solution:
        run.act(a)
    cert_id = run.last["certificate_id"]
    export = web.get("/api/v1/me/export").json()
    assert export["user"]["handle"] == "alice" and len(export["runs"]) == 1 and export["certificates"]
    r = web.post("/api/v1/me/delete", json={"confirm_handle": "wrong"}, headers=WEB)
    assert r.status_code == 422
    assert web.post("/api/v1/me/delete", json={"confirm_handle": "alice"}, headers=WEB).status_code == 200
    cert = TestClient(app).get(f"/api/v1/certificates/{cert_id}").json()
    assert cert["revoked"] and cert["certificate"].get("tombstone")
    r = TestClient(app).post("/api/v1/runs", json={"room": "practice"}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 401


def test_revoked_certificate_says_so(app, solution):
    web, key = api_key(app)
    run = start(web, key)
    for a in solution:
        run.act(a)
    cid = run.last["certificate_id"]
    assert web.post(f"/api/v1/admin/certificates/{cid}/revoke", json={"reason": "abuse"}).status_code == 200
    page = web.get(f"/api/v1/certificates/{cid}").json()
    assert page["revoked"] and page["revocation_reason"] == "abuse"
    assert web.get(f"/api/v1/certificates/{cid}/verify").json()["ok"] is False


def test_ac17_public_mode_rejects_every_admin_call(settings):
    settings.mode = "public"
    settings.signing_key = "nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A="
    app = create_app(settings, embedded_worker=False)
    client = TestClient(app)
    paths = {p: ops for p, ops in app.openapi()["paths"].items() if p.startswith("/api/v1/admin")}
    assert len(paths) >= 10
    for path, ops in paths.items():
        for method in ops:
            concrete = path
            for param in ("{instance_id}", "{job_id}", "{season_id}", "{cert_id}"):
                concrete = concrete.replace(param, "x")
            r = client.request(method.upper(), concrete, json={})
            assert r.status_code == 403, (method, concrete, r.status_code)
            assert r.json()["error"]["code"] == "ADMIN_DISABLED"
    assert client.post("/api/v1/auth/local", json={}).status_code == 403
    app.state.ctx.db.dispose()


def test_local_research_generate_and_batch(app, ctx):
    from escapement_api.worker import Worker

    web = login(app)
    r = web.post("/api/v1/admin/generate", json={"tier": "standard", "seed": "lab", "count": 1})
    assert r.status_code == 200, r.text
    inst = r.json()["instances"][0]
    assert inst["validation"]["passed"]
    job = web.post("/api/v1/admin/jobs", json={"kind": "batch_run", "payload": {"agent": "heuristic", "instance_ids": [inst["room_id"]], "runs": 2}}).json()
    assert Worker(ctx).run_once()
    done = [j for j in web.get("/api/v1/admin/jobs").json()["jobs"] if j["id"] == job["id"]][0]
    assert done["status"] == "done" and done["result"]["summary"]["runs"] == 2


def test_meta_exposes_limits(anon):
    meta = anon.get("/api/v1/meta").json()
    assert meta["limits"]["decision_summary_max"] == 280
    assert meta["tiers"]["hard"]["action_budget"] == 90
    keys = anon.get("/.well-known/escapement-keys.json").json()
    assert keys["keys"][0]["alg"] == "Ed25519"
