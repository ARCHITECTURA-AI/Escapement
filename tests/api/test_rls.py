"""Database-level guarantees on Postgres (AC-03, AC-12): the public API role
cannot read sealed manifests or private run state, and row-level security
enforces ownership and the replay embargo even if a service bug asked."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from .conftest import BACKENDS, api_key, start

pytestmark = pytest.mark.skipif("postgres" not in BACKENDS, reason="needs ESCAPEMENT_TEST_DATABASE_URL")


@pytest.fixture
def pg_app(app, ctx):
    if not ctx.db.postgres:
        pytest.skip("postgres only")
    return app


def test_api_role_cannot_read_sealed_manifests(pg_app, ctx):
    with ctx.db.api.connect() as conn:
        for table in ("sealed_manifests", "run_states", "jobs", "rate_counters"):
            with pytest.raises(ProgrammingError):
                conn.execute(text(f"SELECT * FROM {table} LIMIT 1"))
            conn.rollback()
    with ctx.db.service.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM sealed_manifests")).scalar() >= 1


def test_rls_api_keys_owner_only(pg_app, ctx):
    api_key(pg_app, "alice")
    api_key(pg_app, "bob")
    with ctx.db.api_session(None) as s:
        assert s.execute(text("SELECT count(*) FROM api_keys")).scalar() == 0
    with ctx.db.service_session() as s:
        alice = s.execute(text("SELECT id FROM users WHERE handle='alice'")).scalar()
    with ctx.db.api_session(alice) as s:
        rows = s.execute(text("SELECT user_id FROM api_keys")).scalars().all()
        assert rows and set(rows) == {alice}
        assert s.execute(text("SELECT count(*) FROM user_private")).scalar() == 1


def test_rls_transitions_embargo(pg_app, ctx):
    from datetime import timedelta

    from escapement_api.models import Run
    from escapement_api.timeutil import utcnow

    web, key = api_key(pg_app, "alice")
    run = start(web, key)
    run.act({"tool": "review_journal", "arguments": {}})
    with ctx.db.service_session() as s:
        s.get(Run, run.run_id).embargo_until = utcnow() + timedelta(days=1)
        owner = s.get(Run, run.run_id).user_id
    with ctx.db.api_session(None) as s:
        assert s.execute(text("SELECT count(*) FROM transitions WHERE run_id = :r"), {"r": run.run_id}).scalar() == 0
    with ctx.db.api_session(owner) as s:
        assert s.execute(text("SELECT count(*) FROM transitions WHERE run_id = :r"), {"r": run.run_id}).scalar() == 1


def test_rls_users_update_self_only(pg_app, ctx):
    api_key(pg_app, "alice")
    api_key(pg_app, "bob")
    with ctx.db.service_session() as s:
        alice = s.execute(text("SELECT id FROM users WHERE handle='alice'")).scalar()
    with ctx.db.api_session(alice) as s:
        changed = s.execute(text("UPDATE users SET display_name='x' WHERE handle='bob'")).rowcount
        assert changed == 0
        assert s.execute(text("UPDATE users SET display_name='me' WHERE handle='alice'")).rowcount == 1
