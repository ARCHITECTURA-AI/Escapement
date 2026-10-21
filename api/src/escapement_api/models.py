"""Data model (section 20.1).

Every user-owned table has a user id and a row-level security policy from the
first migration. Sealed manifests live in a table the public API role cannot
read. Private run state (the engine's world state) is likewise service-only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .timeutil import utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


def _ts(nullable: bool = False, default: bool = False) -> Any:
    if default:
        return mapped_column(DateTime(timezone=True), nullable=nullable, default=utcnow)
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    handle: Mapped[str] = mapped_column(String(40), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(80))
    avatar_url: Mapped[str | None] = mapped_column(String(300))
    profile_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts(default=True)
    deleted_at: Mapped[datetime | None] = _ts(nullable=True)


class UserPrivate(Base):
    """The only personal data kept: the GitHub email and id (section 22)."""

    __tablename__ = "user_private"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    github_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie token
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = _ts(default=True)
    expires_at: Mapped[datetime] = _ts()


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = _ts(default=True)
    last_used_at: Mapped[datetime | None] = _ts(nullable=True)
    revoked_at: Mapped[datetime | None] = _ts(nullable=True)


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("user_id", "name", "version_label"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    version_label: Mapped[str] = mapped_column(String(40))
    agent_type: Mapped[str] = mapped_column(String(16), default="outside")  # outside | reference | human
    declared_model: Mapped[str | None] = mapped_column(String(120))  # self-reported
    framework: Mapped[str | None] = mapped_column(String(120))  # self-reported
    memory_strategy: Mapped[str | None] = mapped_column(String(120))  # self-reported
    config_hash: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(60))  # reference runs only, verified
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts(default=True)


class RoomTemplate(Base):
    __tablename__ = "room_templates"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # family:version:tier
    family: Mapped[str] = mapped_column(String(60))
    version: Mapped[str] = mapped_column(String(20))
    engine_version: Mapped[str] = mapped_column(String(20))
    tier: Mapped[str] = mapped_column(String(16))
    difficulty: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    sealed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts(default=True)


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    starts_at: Mapped[datetime] = _ts()
    ends_at: Mapped[datetime] = _ts()
    status: Mapped[str] = mapped_column(String(16), default="scheduled")  # scheduled | open | closed
    released_at: Mapped[datetime | None] = _ts(nullable=True)
    tiers: Mapped[list[str]] = mapped_column(JSONType, default=list)
    instances_per_tier: Mapped[int] = mapped_column(Integer, default=10)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = _ts(default=True)


class RoomInstance(Base):
    __tablename__ = "room_instances"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("room_templates.id"))
    season_id: Mapped[str | None] = mapped_column(ForeignKey("seasons.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # practice | daily | ranked | research
    tier: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(120))
    public_meta: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    instance_hash: Mapped[str] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(String(16), default="passed")
    optimality: Mapped[str] = mapped_column(String(16), default="proven")
    position: Mapped[int] = mapped_column(Integer, default=0)
    manifest_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts(default=True)


class SealedManifest(Base):
    """Private manifests, seeds and verified solutions. The public API role has
    no privileges on this table at all (AC-03)."""

    __tablename__ = "sealed_manifests"
    instance_id: Mapped[str] = mapped_column(ForeignKey("room_instances.id", ondelete="CASCADE"), primary_key=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONType)
    seed: Mapped[str] = mapped_column(String(120))
    solution: Mapped[list[Any]] = mapped_column(JSONType)
    min_length: Mapped[int | None] = mapped_column(Integer)
    validation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = _ts(default=True)


class PublishedManifest(Base):
    """Manifests released for anyone to re-simulate: Practice always, a Daily
    Room after its UTC day, a season's rooms after it closes (12.6, 21.4)."""

    __tablename__ = "published_manifests"
    instance_id: Mapped[str] = mapped_column(ForeignKey("room_instances.id", ondelete="CASCADE"), primary_key=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONType)
    seed: Mapped[str] = mapped_column(String(120))
    solution: Mapped[list[Any]] = mapped_column(JSONType)
    min_length: Mapped[int | None] = mapped_column(Integer)
    optimality: Mapped[str] = mapped_column(String(16), default="proven")
    published_at: Mapped[datetime] = _ts(default=True)


class DailyRoom(Base):
    __tablename__ = "daily_rooms"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    instance_id: Mapped[str] = mapped_column(ForeignKey("room_instances.id"))


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_user_instance", "user_id", "instance_id"),
        Index("ix_runs_agent_instance", "agent_version_id", "instance_id"),
        Index("ix_runs_status_activity", "status", "last_activity_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    agent_version_id: Mapped[str | None] = mapped_column(ForeignKey("agent_versions.id", ondelete="SET NULL"))
    instance_id: Mapped[str] = mapped_column(ForeignKey("room_instances.id"), index=True)
    season_id: Mapped[str | None] = mapped_column(ForeignKey("seasons.id"))
    mode: Mapped[str] = mapped_column(String(16))  # practice | ranked | daily | reference
    agent_type: Mapped[str] = mapped_column(String(16))  # outside | reference | human
    created_via: Mapped[str] = mapped_column(String(16), default="api")  # api | web | mcp | worker
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    actions_used: Mapped[int] = mapped_column(Integer, default=0)
    action_budget: Mapped[int] = mapped_column(Integer)
    malformed_count: Mapped[int] = mapped_column(Integer, default=0)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    chain_hash: Mapped[str] = mapped_column(String(64))
    final_chain_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = _ts(default=True)
    last_activity_at: Mapped[datetime] = _ts(default=True)
    finished_at: Mapped[datetime | None] = _ts(nullable=True)
    wall_time_ms: Mapped[int | None] = mapped_column(Integer)
    declared: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)  # self-reported snapshot
    initial_observation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)  # self-reported
    run_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    api_key_id: Mapped[str | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    embargo_until: Mapped[datetime | None] = _ts(nullable=True)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    certificate_id: Mapped[str | None] = mapped_column(String(40))
    engine_version: Mapped[str] = mapped_column(String(20))
    protocol_version: Mapped[str] = mapped_column(String(10))
    replay_key: Mapped[str | None] = mapped_column(String(200))
    reference_seed: Mapped[str | None] = mapped_column(String(64))
    anon_key: Mapped[str | None] = mapped_column(String(64))  # hashed client fingerprint for anonymous play
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)


class RunState(Base):
    """The engine's private state for a live run. Service role only."""

    __tablename__ = "run_states"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSONType)
    last_result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)


class Transition(Base):
    __tablename__ = "transitions"
    __table_args__ = (
        UniqueConstraint("run_id", "seq"),
        UniqueConstraint("run_id", "action_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    action_id: Mapped[str | None] = mapped_column(String(80))
    request: Mapped[Any] = mapped_column(JSONType)
    action: Mapped[dict[str, Any]] = mapped_column(JSONType)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType)
    observation: Mapped[dict[str, Any]] = mapped_column(JSONType)
    state_hash: Mapped[str] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    malformed: Mapped[bool] = mapped_column(Boolean, default=False)
    system: Mapped[bool] = mapped_column(Boolean, default=False)
    decision_summary: Mapped[str | None] = mapped_column(String(300))  # self-reported
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)  # self-reported
    memory: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)  # first-party agents only
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _ts(default=True)


class Certificate(Base):
    __tablename__ = "certificates"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), unique=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSONType)  # the signed certificate, signature included
    signature: Mapped[str] = mapped_column(String(120))
    key_id: Mapped[str] = mapped_column(String(40))
    issued_at: Mapped[datetime] = _ts(default=True)
    revoked_at: Mapped[datetime | None] = _ts(nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(300))


class SigningKey(Base):
    """Public halves only. Private keys are held outside the repository."""

    __tablename__ = "signing_keys"
    key_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    public_key: Mapped[str] = mapped_column(String(80))
    created: Mapped[str] = mapped_column(String(32))
    retired: Mapped[str | None] = mapped_column(String(32))


class Job(Base):
    """A Postgres-backed jobs table, with no separate broker (19.1)."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "run_after", "priority"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed | cancelled
    priority: Mapped[int] = mapped_column(Integer, default=100)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = _ts(default=True)
    locked_at: Mapped[datetime | None] = _ts(nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _ts(default=True)
    updated_at: Mapped[datetime] = _ts(default=True)


class RateCounter(Base):
    __tablename__ = "rate_counters"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = _ts(default=True)


class HintEvent(Base):
    __tablename__ = "hint_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    milestone_id: Mapped[str] = mapped_column(String(40))
    level: Mapped[int] = mapped_column(Integer)
    at_seq: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts(default=True)


class ModerationReport(Base):
    __tablename__ = "moderation_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reporter_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_type: Mapped[str] = mapped_column(String(20))  # user | agent_version
    target_id: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = _ts(default=True)
    resolved_at: Mapped[datetime | None] = _ts(nullable=True)


class ProductEvent(Base):
    """First-party instrumentation only, no third-party trackers (section 27)."""

    __tablename__ = "product_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    run_id: Mapped[str | None] = mapped_column(String(36))
    props: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = _ts(default=True)


class ReferenceCache(Base):
    """Reference results are cached by room instance hash, agent configuration
    hash and seed, and never rerun (15.3)."""

    __tablename__ = "reference_cache"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = _ts(default=True)


# Tables whose rows belong to a user and carry RLS owner policies.
USER_OWNED = ("user_private", "sessions", "api_keys", "agent_versions", "runs", "certificates", "hint_events")
# Tables the public API role must never read.
SERVICE_ONLY = ("sealed_manifests", "run_states", "jobs", "rate_counters", "reference_cache")
