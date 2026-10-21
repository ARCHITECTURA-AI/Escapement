"""Protocol tests (24.3): stale sequence, wrong prev_hash, duplicate
action_id, tampered chain, one active run per key; plus the acceptance
criteria the run protocol carries."""

import uuid

from escapement_engine.replay import verify_chain

from .conftest import WEB, Runner, api_key, login, start


def test_practice_escape_issues_certificate(app, solution):
    web, key = api_key(app)
    run = start(web, key)
    for a in solution:
        assert run.act(a).status_code == 200
    assert run.last["status"] == "escaped"
    cert_id = run.last["certificate_id"]
    assert cert_id
    cert = web.get(f"/api/v1/certificates/{cert_id}").json()
    body = cert["certificate"]
    assert body["outcome"] == "escaped" and body["actions_used"] == len(solution)
    assert body["agent"]["model"] == "gpt-test" and "agent.model" in body["self_reported_fields"]
    assert body["run_set"] == {"runs": 1, "escapes": 1}
    assert cert["verification"]["available"] == "full"
    report = web.get(f"/api/v1/certificates/{cert_id}/verify").json()
    assert report["ok"] and report["level"] == "full"


def test_stale_sequence_and_wrong_prev_hash(app):
    web, key = api_key(app)
    run = start(web, key)
    run.act({"tool": "review_journal", "arguments": {}})
    body = {"expected_sequence": 1, "action_id": "x1", "prev_hash": run.hash, "tool": "review_journal", "arguments": {}}
    r = web.post(f"/api/v1/runs/{run.run_id}/actions", json=body, headers=run.auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_SEQUENCE"
    body = {"expected_sequence": 2, "action_id": "x2", "prev_hash": "0" * 64, "tool": "review_journal", "arguments": {}}
    r = web.post(f"/api/v1/runs/{run.run_id}/actions", json=body, headers=run.auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CHAIN_MISMATCH"
    assert r.json()["error"]["details"]["chain_hash"] == run.hash


def test_ac09_duplicate_action_id_is_not_executed_again(app):
    web, key = api_key(app)
    run = start(web, key)
    body = {"expected_sequence": 1, "action_id": "same-id", "prev_hash": run.hash, "tool": "review_journal", "arguments": {}}
    first = web.post(f"/api/v1/runs/{run.run_id}/actions", json=body, headers=run.auth)
    again = web.post(f"/api/v1/runs/{run.run_id}/actions", json=body, headers=run.auth)
    assert first.status_code == again.status_code == 200
    assert again.headers.get("Idempotent-Replay") == "true"
    assert first.json() == again.json()
    obs = web.get(f"/api/v1/runs/{run.run_id}/observation", headers=run.auth).json()
    assert obs["sequence"] == 1 and obs["observation"]["actions_used"] == 1


def test_one_active_run_per_key_per_room(app):
    web, key = api_key(app)
    first = start(web, key)
    r = web.post(
        "/api/v1/runs", json={"room": "practice", "agent": {"name": "a", "version": "1"}}, headers={"Authorization": f"Bearer {key}"}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACTIVE_RUN_EXISTS"
    assert r.json()["error"]["details"]["run_id"] == first.run_id
    r = web.post("/api/v1/runs", json={"room": "practice", "replace_active": True}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 201
    old = web.get(f"/api/v1/runs/{first.run_id}").json()
    assert old["status"] == "client_aborted"


def test_run_token_required(app):
    web, key = api_key(app)
    run = start(web, key)
    body = {"expected_sequence": 1, "action_id": "a", "prev_hash": run.hash, "tool": "review_journal", "arguments": {}}
    assert web.post(f"/api/v1/runs/{run.run_id}/actions", json=body).status_code == 401
    assert web.post(f"/api/v1/runs/{run.run_id}/actions", json=body, headers={"Authorization": f"Bearer {key}"}).status_code == 401
    assert web.post(f"/api/v1/runs/{run.run_id}/actions", json=body, headers={"X-Run-Token": run.token}).status_code == 200


def test_malformed_recorded_free_and_limited(app):
    web, key = api_key(app)
    run = start(web, key)
    r = run.act({"tool": "teleport", "arguments": {}})
    assert r.status_code == 200 and r.json()["result"]["malformed"] and r.json()["result"]["cost"] == 0
    assert r.json()["observation"]["actions_used"] == 0
    run.act({"tool": "inspect"})
    r = run.act({"arguments": {"x": 1}})
    assert r.json()["status"] == "malformed_limit_reached"


def test_ac08_no_action_after_terminal(app):
    web, key = api_key(app)
    run = start(web, key)
    done = run.finish()
    assert done["status"] == "client_aborted" and done["certificate_id"]
    r = run.act({"tool": "review_journal", "arguments": {}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EPISODE_FINISHED"
    replay = web.get(f"/api/v1/runs/{run.run_id}/replay").json()["replay"]
    assert [s["action"]["tool"] for s in replay["steps"]] == ["system.end"]


def test_ac07_claimed_success_is_not_escape(app):
    web, key = api_key(app)
    run = start(web, key)
    r = run.act({"tool": "move", "arguments": {"destination_id": "exterior"}}, decision_summary="I unlocked the door and escaped.")
    assert r.json()["result"]["error"] == "UNKNOWN_TARGET"
    done = run.finish()
    assert done["status"] == "client_aborted"
    cert = web.get(f"/api/v1/certificates/{done['certificate_id']}").json()["certificate"]
    assert cert["outcome"] != "escaped"


def test_decision_summary_capped_and_labelled(app):
    web, key = api_key(app)
    run = start(web, key)
    run.act({"tool": "review_journal", "arguments": {}}, decision_summary="<b>x</b>" * 100)
    replay = web.get(f"/api/v1/runs/{run.run_id}/replay").json()["replay"]
    assert len(replay["steps"][0]["decision_summary"]) == 280
    assert "self-reported" in replay["self_reported"]["note"] or "reported by the client" in replay["self_reported"]["note"]


def test_payload_limit(app):
    web, key = api_key(app)
    run = start(web, key)
    huge = {"expected_sequence": 1, "action_id": "a", "prev_hash": run.hash, "tool": "inspect", "arguments": {"target_id": "x" * 20000}}
    r = web.post(f"/api/v1/runs/{run.run_id}/actions", json=huge, headers=run.auth)
    assert r.status_code == 413


def test_tampered_replay_fails_chain(app, solution):
    web, key = api_key(app)
    run = start(web, key)
    for a in solution[:5]:
        run.act(a)
    run.finish()
    replay = web.get(f"/api/v1/runs/{run.run_id}/replay").json()["replay"]
    assert verify_chain(replay).ok
    replay["steps"][1]["result"]["message"] = "edited"
    assert not verify_chain(replay).ok


def test_usage_is_self_reported(app):
    web, key = api_key(app)
    run = start(web, key)
    run.act({"tool": "review_journal", "arguments": {}}, usage={"tokens_in": 900, "tokens_out": 40, "cost_usd": 0.0012})
    done = web.post(f"/api/v1/runs/{run.run_id}/finish", json={"usage": {"model_decisions": 1}}, headers=run.auth).json()
    cert = web.get(f"/api/v1/certificates/{done['certificate_id']}").json()["certificate"]
    assert cert["usage"]["tokens_in"] == 900 and cert["usage"]["cost_usd_micros"] == 1200 and cert["usage"]["model_decisions"] == 1
    assert "usage.cost_usd_micros" in cert["self_reported_fields"]


def test_anonymous_human_practice(anon, solution):
    run = start(anon, None, headers=WEB, agent_type="human")
    for a in solution:
        run.act(a)
    assert run.last["status"] == "escaped"
    assert run.last["certificate_id"] is None  # certificates need an account
    assert anon.post("/api/v1/runs", json={"room": "daily", "agent_type": "human"}).status_code == 401


def test_idle_timeout_ends_cleanly(app, ctx):
    from datetime import timedelta

    from escapement_api.models import Run

    web, key = api_key(app)
    run = start(web, key)
    with ctx.db.service_session() as s:
        row = s.get(Run, run.run_id)
        row.last_activity_at = row.last_activity_at - timedelta(minutes=11)
    assert ctx.runs.expire_stale() == 1
    summary = web.get(f"/api/v1/runs/{run.run_id}").json()
    assert summary["status"] == "idle_timeout" and summary["certificate_id"]


def test_kill_switch(app, ctx):
    web, key = api_key(app)
    run = start(web, key)
    r = web.post("/api/v1/admin/kill-switch", json={"on": True})
    assert r.json()["cancelled_runs"] == 1
    assert web.get(f"/api/v1/runs/{run.run_id}").json()["status"] == "cancelled"
    r = web.post("/api/v1/runs", json={"room": "practice"}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ARENA_PAUSED"


def test_daily_run_cap(app, ctx):
    ctx.settings.daily_run_cap = 2
    ctx.settings.new_account_daily_run_cap = 2
    web, key = api_key(app)
    for _ in range(2):
        start(web, key, replace_active=True)
    r = web.post("/api/v1/runs", json={"room": "practice", "replace_active": True}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_revoked_key_rejected(app):
    web, key = api_key(app)
    keys = web.get("/api/v1/me/keys").json()["keys"]
    web.delete(f"/api/v1/me/keys/{keys[0]['id']}", headers=WEB)
    r = web.post("/api/v1/runs", json={"room": "practice"}, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 401


def test_csrf_header_required_for_cookie_writes(app):
    web = login(app)
    assert web.post("/api/v1/me/keys", json={"name": "x"}).status_code == 403
    assert web.post("/api/v1/me/keys", json={"name": "x"}, headers=WEB).status_code == 201
