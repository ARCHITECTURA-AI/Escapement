"""The run service: the server side of the run protocol (sections 13.1, 20).

1. Create a run, authenticated with an API key (or a browser session for
   humans), naming a room, an agent version and declared metadata.
2. Act: each request carries expected_sequence, action_id and prev_hash. The
   server validates it, applies it in the engine, extends the chain and
   returns the result and the new chain hash.
3. Finish on escape, on any terminal budget condition, on client request, or
   after the idle timeout.
4. Certify: the server signs a certificate per run and summarises runs on the
   same instance as a run set.

A transition is persisted before its result is returned. A repeated
action_id returns the recorded result without executing again. Actions in a
run are serialised by a row lock.
"""

from __future__ import annotations

import math
import re
from datetime import timedelta
from typing import Any

from escapement_engine.core import Episode, EpisodeFinished
from escapement_engine.core.world import CompiledRoom
from escapement_engine.replay import build_replay, room_meta
from escapement_engine.schemas.endings import (
    CANCELLED,
    CLIENT_ABORTED,
    IDLE_TIMEOUT,
    IN_PROGRESS,
    INFRASTRUCTURE_ENDINGS,
    REFERENCE_PROVIDER_FAILURE,
    WALL_CLOCK_EXCEEDED,
)
from escapement_engine.version import ENGINE_VERSION, PROTOCOL_VERSION
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import Principal
from ..errors import APIError, not_found, unauthorized
from ..models import AgentVersion, RoomInstance, Run, RunState, Season, Setting, Transition
from ..ratelimit import hit
from ..security import matches, new_run_token, sha256_hex
from ..timeutil import as_utc, day_end, iso, utc_today, utcnow
from .rooms import ensure_practice, get_or_create_daily, load_room, room_public, season_status

HEX64 = re.compile(r"^[0-9a-f]{64}$")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._\-+/]{0,59}$")


def clean_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise APIError(422, "INVALID_REQUEST", "Text fields must be strings.")
    value = CONTROL.sub("", value).strip()
    return value[:limit] or None


def clean_usage(raw: Any) -> dict[str, int]:
    """Self-reported usage. Stored as integers; cost in micro-dollars."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise APIError(422, "INVALID_REQUEST", "'usage' must be an object.")
    out: dict[str, int] = {}
    for key in ("tokens_in", "tokens_out", "model_decisions"):
        v = raw.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0:
            out[key] = int(v)
    cost = raw.get("cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
        out["cost_usd_micros"] = int(round(cost * 1_000_000))
    return out


def add_usage(total: dict[str, Any], delta: dict[str, int]) -> dict[str, Any]:
    out = dict(total or {})
    for k, v in delta.items():
        out[k] = int(out.get(k, 0)) + v
    return out


class RunService:
    def __init__(self, ctx) -> None:  # type: ignore[no-untyped-def]
        self.ctx = ctx

    @property
    def settings(self):  # type: ignore[no-untyped-def]
        return self.ctx.settings

    # ------------------------------------------------------------------ guards

    def kill_switch_on(self, s: Session) -> bool:
        if self.settings.kill_switch:
            return True
        row = s.get(Setting, "kill_switch")
        return bool(row and row.value)

    def _caps(self, s: Session, p: Principal, fingerprint: str) -> None:
        st = self.settings
        if p.api_key_id:
            hit(s, f"key:{p.api_key_id}", st.rate_per_key_per_min)
        if p.user_id and not p.is_system:
            hit(s, f"user:{p.user_id}", st.rate_per_user_per_min)
        else:
            hit(s, f"anon:{fingerprint}", st.rate_anonymous_per_min)
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        total_today = s.execute(select(func.count()).select_from(Run).where(Run.started_at >= start)).scalar_one()
        if total_today >= st.global_daily_run_ceiling:
            raise APIError(
                503,
                "GLOBAL_CEILING",
                "The arena has reached today's global run ceiling. Try again after 00:00 UTC.",
                headers={"Retry-After": str(int((day_end(utc_today()) - utcnow()).total_seconds()))},
            )
        if p.user_id and not p.is_system:
            mine = s.execute(select(func.count()).select_from(Run).where(Run.user_id == p.user_id, Run.started_at >= start)).scalar_one()
            new = p.created_at is not None and utcnow() - p.created_at < timedelta(days=st.new_account_days)
            cap = st.new_account_daily_run_cap if new else st.daily_run_cap
            if mine >= cap:
                raise APIError(
                    429,
                    "DAILY_RUN_CAP",
                    f"You have used all {cap} runs for today" + (" (new accounts start with a lower cap)" if new else "") + ".",
                    {"cap": cap},
                    {"Retry-After": str(int((day_end(utc_today()) - utcnow()).total_seconds()))},
                )

    # ------------------------------------------------------------------ create

    def create(self, p: Principal, body: dict[str, Any], fingerprint: str, via: str) -> dict[str, Any]:
        st = self.settings
        with self.ctx.db.service_session() as s:
            if self.kill_switch_on(s):
                raise APIError(503, "ARENA_PAUSED", "The arena is paused by its operators. No new runs can start.")
            agent_type = self._agent_type(p, body)
            self._caps(s, p, fingerprint)
            inst, season = self._resolve_room(s, p, str(body.get("room") or "practice"))
            mode = (
                "reference"
                if agent_type == "reference"
                else {"practice": "practice", "daily": "daily", "ranked": "ranked", "research": "practice"}[inst.kind]
            )
            if not p.signed_in and inst.kind != "practice":
                raise unauthorized("Sign in to play this room. Practice is open to everyone.")
            if inst.kind == "ranked" and agent_type == "human":
                raise APIError(403, "AGENTS_ONLY", "Ranked rooms are for agents. Humans can play Practice and the Daily Room.")

            version, declared = self._agent_version(s, p, body, agent_type, ranked=inst.kind == "ranked")
            if inst.kind == "ranked" and agent_type != "reference" and version is not None:
                used = s.execute(
                    select(func.count())
                    .select_from(Run)
                    .where(
                        Run.agent_version_id == version.id,
                        Run.instance_id == inst.id,
                        Run.status.notin_(INFRASTRUCTURE_ENDINGS),
                    )
                ).scalar_one()
                if used >= st.certified_runs_per_instance:
                    raise APIError(
                        409,
                        "RUN_LIMIT",
                        f"This agent version already has {st.certified_runs_per_instance} certified runs on this instance. "
                        "Register a new agent version or choose another instance.",
                    )
            if inst.kind == "daily":
                board = "humans" if agent_type == "human" else "agents"
                types = ["human"] if board == "humans" else ["outside", "reference"]
                used = s.execute(
                    select(func.count())
                    .select_from(Run)
                    .where(Run.user_id == p.user_id, Run.instance_id == inst.id, Run.agent_type.in_(types))
                ).scalar_one()
                if used >= st.daily_attempts:
                    raise APIError(
                        409,
                        "DAILY_ATTEMPTS",
                        f"You have used all {st.daily_attempts} attempts on today's Daily Room for the {board} board.",
                    )

            self._one_active(s, p, inst.id, fingerprint, replace=bool(body.get("replace_active")))

            room = load_room(s, inst.id)
            token, token_hash = new_run_token()
            run = Run(
                user_id=p.user_id,
                agent_version_id=version.id if version else None,
                instance_id=inst.id,
                season_id=inst.season_id,
                mode=mode,
                agent_type=agent_type,
                created_via=via,
                action_budget=room.manifest.budget.actions,
                run_token_hash=token_hash,
                api_key_id=p.api_key_id,
                engine_version=ENGINE_VERSION,
                protocol_version=PROTOCOL_VERSION,
                declared=declared,
                embargo_until=self._embargo(inst, season),
                anon_key=None if p.signed_in else fingerprint,
                reference_seed=clean_text(body.get("reference_seed"), 64) if agent_type == "reference" else None,
                chain_hash="",
            )
            s.add(run)
            s.flush()
            ep = Episode.start(room, run.id)
            run.chain_hash = ep.chain_hash
            run.initial_observation = ep.observation()
            s.add(RunState(run_id=run.id, state=ep.state, last_result=None))
            s.flush()
            return {
                "run_id": run.id,
                "run_token": token,
                "protocol_version": PROTOCOL_VERSION,
                "engine_version": ENGINE_VERSION,
                "mode": mode,
                "agent_type": agent_type,
                "room": room_public(inst, season),
                "agent": declared,
                "observation": run.initial_observation,
                "sequence": 0,
                "chain_hash": ep.chain_hash,
                "status": IN_PROGRESS,
                "limits": {
                    "action_budget": room.manifest.budget.actions,
                    "malformed_limit": room.manifest.budget.malformed,
                    "idle_timeout_s": st.idle_timeout_s,
                    "wall_clock_s": st.wall_clock_s,
                    "decision_summary_max": st.decision_summary_max,
                    "payload_limit_bytes": st.payload_limit_bytes,
                },
                "watch_url": f"{st.web_base_url}/runs/{run.id}",
            }

    def _agent_type(self, p: Principal, body: dict[str, Any]) -> str:
        if p.is_system:
            return "reference"
        requested = body.get("agent_type")
        if p.via in ("session", "anonymous") and requested in (None, "human"):
            if p.via == "anonymous" and requested != "human":
                raise unauthorized("Pass an API key to run an agent, or play as a human in the browser.")
            return "human"
        if p.via == "anonymous":
            raise unauthorized()
        if requested == "human":
            raise APIError(422, "INVALID_REQUEST", "API keys run agents; humans play in the browser.")
        return "outside"

    def _resolve_room(self, s: Session, p: Principal, room: str) -> tuple[RoomInstance, Season | None]:
        if room == "practice":
            return ensure_practice(s), None
        if room == "daily" or room == f"daily-{utc_today().isoformat()}":
            return get_or_create_daily(s, self.settings), None
        if room.startswith("daily-"):
            raise APIError(409, "DAILY_CLOSED", "Only today's Daily Room (UTC) is playable.")
        inst = s.get(RoomInstance, room)
        if inst is None:
            raise not_found(f"Unknown room '{room}'. Use 'practice', 'daily' or a ranked instance id.")
        season = s.get(Season, inst.season_id) if inst.season_id else None
        if inst.kind == "ranked":
            status = season_status(season) if season else "closed"
            if status != "open":
                raise APIError(409, "SEASON_NOT_OPEN", f"This room's season is {status}; ranked runs are not accepted.")
        elif inst.kind == "research" and self.settings.mode != "local":
            raise not_found("Unknown room.")
        return inst, season

    def _embargo(self, inst: RoomInstance, season: Season | None):  # type: ignore[no-untyped-def]
        if inst.kind == "ranked" and season is not None:
            return as_utc(season.released_at) if season.status == "closed" else as_utc(season.ends_at)
        if inst.kind == "daily":
            from datetime import date

            return day_end(date.fromisoformat(inst.id.removeprefix("daily-")))
        return None

    def _agent_version(
        self, s: Session, p: Principal, body: dict[str, Any], agent_type: str, ranked: bool
    ) -> tuple[AgentVersion | None, dict[str, Any]]:
        if agent_type == "human":
            return None, {"name": "Human player", "version": None, "agent_type": "human"}
        vid = body.get("agent_version_id")
        if vid:
            version = s.get(AgentVersion, vid)
            if version is None or version.user_id != p.user_id:
                raise not_found("Unknown agent version.")
        else:
            agent = body.get("agent") or {}
            if not isinstance(agent, dict):
                raise APIError(422, "INVALID_REQUEST", "'agent' must be an object.")
            if ranked and not agent.get("name"):
                raise APIError(422, "AGENT_REQUIRED", "Ranked runs need a declared agent: name and version.")
            name = clean_text(agent.get("name"), 60) or "my-agent"
            label = clean_text(agent.get("version"), 40) or "0.1.0"
            if not NAME_RE.match(name) or not NAME_RE.match(label):
                raise APIError(422, "INVALID_REQUEST", "Agent name and version may use letters, digits, spaces and ._-+/ only.")
            version = s.execute(
                select(AgentVersion).where(
                    AgentVersion.user_id == p.user_id, AgentVersion.name == name, AgentVersion.version_label == label
                )
            ).scalar_one_or_none()
            fields = {
                "declared_model": clean_text(agent.get("model"), 120),
                "framework": clean_text(agent.get("framework"), 120),
                "memory_strategy": clean_text(agent.get("memory"), 120),
            }
            if version is None:
                config_hash = agent.get("config_hash")
                if not (isinstance(config_hash, str) and HEX64.match(config_hash)):
                    config_hash = sha256_hex(repr(sorted((k, v or "") for k, v in fields.items())) + name + label)
                version = AgentVersion(
                    user_id=p.user_id,  # type: ignore[arg-type]
                    name=name,
                    version_label=label,
                    agent_type=agent_type,
                    config_hash=config_hash,
                    provider=clean_text(body.get("provider"), 60) if agent_type == "reference" else None,
                    **fields,
                )
                s.add(version)
                s.flush()
        declared = {
            "agent_version_id": version.id,
            "name": version.name,
            "version": version.version_label,
            "agent_type": agent_type,
            "model": version.declared_model,
            "framework": version.framework,
            "memory": version.memory_strategy,
            "config_hash": version.config_hash,
            "provider": version.provider,
            "model_attested": agent_type == "reference",
        }
        return version, declared

    def _one_active(self, s: Session, p: Principal, instance_id: str, fingerprint: str, replace: bool) -> None:
        q = select(Run).where(Run.instance_id == instance_id, Run.status == IN_PROGRESS)
        if p.api_key_id:
            q = q.where(Run.api_key_id == p.api_key_id)
        elif p.user_id:
            q = q.where(Run.user_id == p.user_id, Run.api_key_id.is_(None))
        else:
            q = q.where(Run.anon_key == fingerprint)
        for run in s.execute(q.with_for_update()).scalars().all():
            if self._expire_if_stale(s, run):
                continue
            if replace:
                self._terminate(s, run, CLIENT_ABORTED, "Replaced by a new run.")
                continue
            raise APIError(
                409,
                "ACTIVE_RUN_EXISTS",
                "You already have an active run in this room. Resume it with its run token, finish it, or pass replace_active.",
                {"run_id": run.id, "sequence": run.seq, "chain_hash": run.chain_hash},
            )

    # ------------------------------------------------------------------ act

    def _load(self, s: Session, run_id: str, token: str | None, lock: bool = True) -> Run:
        q = select(Run).where(Run.id == run_id)
        if lock:
            q = q.with_for_update()
        run = s.execute(q).scalar_one_or_none()
        if run is None:
            raise not_found("Unknown run.")
        if not token or not matches(token, run.run_token_hash):
            raise unauthorized("This call needs the run's token (returned when the run was created).")
        return run

    def act(self, run_id: str, token: str | None, body: Any) -> tuple[dict[str, Any], bool]:
        if not isinstance(body, dict):
            raise APIError(422, "INVALID_REQUEST", "The body must be a JSON object.")
        seq = body.get("expected_sequence")
        action_id = body.get("action_id")
        prev_hash = body.get("prev_hash")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            raise APIError(422, "INVALID_REQUEST", "'expected_sequence' must be a positive integer.")
        if not isinstance(action_id, str) or not (1 <= len(action_id) <= 80):
            raise APIError(422, "INVALID_REQUEST", "'action_id' must be a string of 1 to 80 characters (a client-generated UUID).")
        if not isinstance(prev_hash, str) or not HEX64.match(prev_hash):
            raise APIError(422, "INVALID_REQUEST", "'prev_hash' must be the hex chain hash from the previous response.")
        with self.ctx.db.service_session() as s:
            run = self._load(s, run_id, token)
            if run.agent_type != "reference":  # first-party runs are paced by the drip queue
                limiter = f"user:{run.user_id}" if run.user_id else f"anon:{run.anon_key}"
                hit(s, limiter, self.settings.rate_per_user_per_min)
            recorded = s.execute(
                select(Transition).where(Transition.run_id == run.id, Transition.action_id == action_id)
            ).scalar_one_or_none()
            if recorded is not None:
                return self._response(recorded, run), True
            if run.status == IN_PROGRESS and self._expire_if_stale(s, run):
                pass
            if run.status != IN_PROGRESS:
                raise APIError(
                    409,
                    "EPISODE_FINISHED",
                    f"The run has ended ({run.status}). No further actions execute.",
                    {"status": run.status, "sequence": run.seq, "chain_hash": run.chain_hash, "certificate_id": run.certificate_id},
                )
            if seq != run.seq + 1:
                raise APIError(
                    409,
                    "STALE_SEQUENCE",
                    f"Expected sequence {run.seq + 1}, got {seq}.",
                    {"sequence": run.seq, "chain_hash": run.chain_hash},
                )
            if prev_hash != run.chain_hash:
                raise APIError(
                    409,
                    "CHAIN_MISMATCH",
                    "prev_hash does not match the server's chain.",
                    {"sequence": run.seq, "chain_hash": run.chain_hash},
                )
            room = load_room(s, run.instance_id)
            rs = s.get(RunState, run.id)
            ep = Episode.resume(room, run.id, rs.state, run.chain_hash, rs.last_result)  # type: ignore[union-attr]
            request = {k: body[k] for k in ("tool", "arguments") if k in body}
            started = utcnow()
            try:
                rec = ep.step(request)
            except EpisodeFinished:  # pragma: no cover - guarded above
                raise APIError(409, "EPISODE_FINISHED", "The run has ended.")
            usage = clean_usage(body.get("usage"))
            memory = body.get("memory") if run.agent_type == "reference" and isinstance(body.get("memory"), dict) else None
            t = Transition(
                run_id=run.id,
                seq=rec.seq,
                action_id=action_id,
                request=request,
                action=rec.action,
                result=rec.result,
                observation=rec.observation,
                state_hash=rec.state_hash,
                chain_hash=rec.chain_hash,
                status=rec.status,
                malformed=rec.malformed,
                decision_summary=clean_text(body.get("decision_summary"), self.settings.decision_summary_max),
                usage=usage or None,
                memory=memory,
                elapsed_ms=int((utcnow() - as_utc(run.last_activity_at)).total_seconds() * 1000),  # type: ignore[operator]
            )
            s.add(t)
            rs.state = ep.state  # type: ignore[union-attr]
            rs.last_result = ep.last_result  # type: ignore[union-attr]
            run.seq = rec.seq
            run.chain_hash = rec.chain_hash
            run.actions_used = ep.state["used"]
            run.malformed_count = ep.state["mal_total"]
            run.status = rec.status
            run.last_activity_at = started
            if usage:
                run.usage = add_usage(run.usage, usage)
            s.flush()
            if ep.finished:
                self._finalize(s, run, room)
            return self._response(t, run), False

    def _response(self, t: Transition, run: Run) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "sequence": t.seq,
            "result": t.result,
            "observation": t.observation,
            "chain_hash": t.chain_hash,
            "status": t.status,
            "certificate_id": run.certificate_id if t.status != IN_PROGRESS else None,
        }

    def observation(self, run_id: str, token: str | None) -> dict[str, Any]:
        with self.ctx.db.service_session() as s:
            run = self._load(s, run_id, token)
            self._expire_if_stale(s, run)
            last = s.execute(
                select(Transition).where(Transition.run_id == run.id).order_by(Transition.seq.desc()).limit(1)
            ).scalar_one_or_none()
            obs = last.observation if last else run.initial_observation
            return {
                "run_id": run.id,
                "sequence": run.seq,
                "chain_hash": run.chain_hash,
                "status": run.status,
                "observation": obs,
                "certificate_id": run.certificate_id,
            }

    def finish(self, run_id: str, token: str | None, body: dict[str, Any] | None) -> dict[str, Any]:
        body = body or {}
        with self.ctx.db.service_session() as s:
            run = self._load(s, run_id, token)
            totals = clean_usage(body.get("usage"))
            if totals:
                run.usage = {**(run.usage or {}), **totals}
            if run.status == IN_PROGRESS and not self._expire_if_stale(s, run):
                if body.get("reason") == REFERENCE_PROVIDER_FAILURE and run.agent_type == "reference":
                    # Infrastructure, not an agent failure: kept distinct in every report.
                    self._terminate(s, run, REFERENCE_PROVIDER_FAILURE, "The reference model provider failed.")
                else:
                    self._terminate(s, run, CLIENT_ABORTED, "Run ended by the client.")
            elif run.status != IN_PROGRESS and run.certificate_id is None and run.user_id:
                self._finalize(s, run, load_room(s, run.instance_id))
            return {
                "run_id": run.id,
                "status": run.status,
                "sequence": run.seq,
                "final_chain_hash": run.final_chain_hash,
                "actions_used": run.actions_used,
                "certificate_id": run.certificate_id,
                "certificate_url": f"{self.settings.web_base_url}/c/{run.certificate_id}" if run.certificate_id else None,
            }

    # ------------------------------------------------------------------ endings

    def _expire_if_stale(self, s: Session, run: Run) -> bool:
        if run.status != IN_PROGRESS:
            return False
        now = utcnow()
        if now - as_utc(run.started_at) > timedelta(seconds=self.settings.wall_clock_s):  # type: ignore[operator]
            self._terminate(s, run, WALL_CLOCK_EXCEEDED)
            return True
        if now - as_utc(run.last_activity_at) > timedelta(seconds=self.settings.idle_timeout_s):  # type: ignore[operator]
            self._terminate(s, run, IDLE_TIMEOUT)
            return True
        return False

    def _terminate(self, s: Session, run: Run, ending: str, note: str | None = None) -> None:
        room = load_room(s, run.instance_id)
        rs = s.get(RunState, run.id)
        ep = Episode.resume(room, run.id, rs.state, run.chain_hash, rs.last_result)  # type: ignore[union-attr]
        rec = ep.terminate(ending, note=note)
        s.add(
            Transition(
                run_id=run.id,
                seq=rec.seq,
                action_id=None,
                request={"tool": "system.end", "arguments": {"ending": ending}},
                action=rec.action,
                result=rec.result,
                observation=rec.observation,
                state_hash=rec.state_hash,
                chain_hash=rec.chain_hash,
                status=rec.status,
                system=True,
            )
        )
        rs.state = ep.state  # type: ignore[union-attr]
        rs.last_result = ep.last_result  # type: ignore[union-attr]
        run.seq = rec.seq
        run.chain_hash = rec.chain_hash
        run.status = ending
        s.flush()
        self._finalize(s, run, room)

    def expire_stale(self) -> int:
        """Sweeper: end idle and over-time runs cleanly with a recorded status."""
        st = self.settings
        now = utcnow()
        with self.ctx.db.service_session() as s:
            ids = (
                s.execute(
                    select(Run.id).where(
                        Run.status == IN_PROGRESS,
                        (Run.last_activity_at < now - timedelta(seconds=st.idle_timeout_s))
                        | (Run.started_at < now - timedelta(seconds=st.wall_clock_s)),
                    )
                )
                .scalars()
                .all()
            )
        count = 0
        for rid in ids:
            with self.ctx.db.service_session() as s:
                run = s.execute(select(Run).where(Run.id == rid).with_for_update()).scalar_one()
                if self._expire_if_stale(s, run):
                    count += 1
        return count

    def cancel_live(self, reason: str = "Cancelled by the operators (kill switch).") -> int:
        with self.ctx.db.service_session() as s:
            ids = s.execute(select(Run.id).where(Run.status == IN_PROGRESS)).scalars().all()
        for rid in ids:
            with self.ctx.db.service_session() as s:
                run = s.execute(select(Run).where(Run.id == rid).with_for_update()).scalar_one()
                if run.status == IN_PROGRESS:
                    self._terminate(s, run, CANCELLED, reason)
        return len(ids)

    # ------------------------------------------------------------------ finalize

    def _finalize(self, s: Session, run: Run, room: CompiledRoom) -> None:
        from .certs import issue_certificate

        now = utcnow()
        run.finished_at = now
        run.final_chain_hash = run.chain_hash
        run.wall_time_ms = int((now - as_utc(run.started_at)).total_seconds() * 1000)  # type: ignore[operator]
        s.flush()
        replay = build_run_replay(s, run, room)
        if run.user_id is not None:
            issue_certificate(self.ctx, s, run, room)
            replay["certificate_id"] = run.certificate_id
        try:
            run.replay_key = self.ctx.store.put(run.id, replay)
        except Exception:  # pragma: no cover - storage outage must not lose the run
            run.replay_key = None


def build_run_replay(s: Session, run: Run, room: CompiledRoom | None = None, include_memory: bool = False) -> dict[str, Any]:
    inst = s.get(RoomInstance, run.instance_id)
    rows = s.execute(select(Transition).where(Transition.run_id == run.id).order_by(Transition.seq)).scalars().all()
    steps = []
    for t in rows:
        step = {
            "seq": t.seq,
            "request": t.request,
            "action": t.action,
            "result": t.result,
            "observation": t.observation,
            "state_hash": t.state_hash,
            "chain_hash": t.chain_hash,
            "status": t.status,
            "malformed": t.malformed,
            "system": t.system,
            "elapsed_ms": t.elapsed_ms,
        }
        if t.decision_summary:
            step["decision_summary"] = t.decision_summary
        if t.usage:
            step["usage"] = t.usage
        if include_memory and t.memory:
            step["memory"] = t.memory
        steps.append(step)
    meta = (
        room_meta(room.manifest, run.season_id)
        if room is not None
        else {
            "room_id": inst.id,  # type: ignore[union-attr]
            "title": inst.title,  # type: ignore[union-attr]
            "tier": inst.tier,  # type: ignore[union-attr]
            "family": (inst.public_meta or {}).get("family"),  # type: ignore[union-attr]
            "template_version": (inst.public_meta or {}).get("template_version"),  # type: ignore[union-attr]
            "instance_hash": inst.instance_hash,  # type: ignore[union-attr]
            "season": run.season_id,
            "action_budget": run.action_budget,
        }
    )
    meta["kind"] = inst.kind if inst else None
    return build_replay(
        run_id=run.id,
        room=meta,
        mode=run.mode,
        agent=run.declared,
        initial_observation=run.initial_observation,
        steps=steps,
        outcome=run.status,
        final_chain_hash=run.chain_hash,
        usage=run.usage,
        engine_version=run.engine_version,
        protocol_version=run.protocol_version,
        started_at=iso(run.started_at),
        finished_at=iso(run.finished_at),
        wall_time_ms=run.wall_time_ms,
        extra={"certificate_id": run.certificate_id} if run.certificate_id else None,
    )
