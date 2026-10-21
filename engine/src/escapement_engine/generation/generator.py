"""Seeded generation (section 12.1).

    Select template and tier
      instantiate objects and dependencies
      assign valid locations
      generate clue values from the seed
      search for a solution using the real engine's action semantics
      replay the solution in the real engine
      run the validation suite
      publish a versioned, hashed room manifest

An instance is reproducible from (family, template version, tier, seed) and
the engine version. A seed whose instance fails validation is retried with a
derived sub-seed (`seed#1`, `seed#2`, ...); the attempt number is recorded in
the manifest seed so the result is still reproducible.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from ..core.episode import instance_hash
from ..rooms import emergency_lockdown
from ..schemas.manifest import RoomManifest
from ..validation.suite import ValidationReport, validate

FAMILIES = {emergency_lockdown.FAMILY: emergency_lockdown}
PRACTICE_SEED = "practice-v1"
PRACTICE_ROOM_ID = "practice"


class GenerationError(RuntimeError):
    pass


@dataclass
class GeneratedInstance:
    manifest: RoomManifest
    instance_hash: str
    solution: list[dict[str, Any]]
    intended: list[dict[str, Any]]
    min_length: int | None
    optimality: str
    report: ValidationReport
    attempts: int

    def summary(self) -> dict[str, Any]:
        return {
            "room_id": self.manifest.room_id,
            "tier": self.manifest.tier,
            "family": self.manifest.family,
            "template_version": self.manifest.template_version,
            "engine_version": self.manifest.engine_version,
            "instance_hash": self.instance_hash,
            "min_length": self.min_length,
            "optimality": self.optimality,
            "attempts": self.attempts,
            "validation": self.report.to_dict(),
        }


def generate(tier: str, seed: str, room_id: str, family: str = emergency_lockdown.FAMILY, max_attempts: int = 16) -> GeneratedInstance:
    template = FAMILIES[family]
    failures: list[str] = []
    for attempt in range(max_attempts):
        manifest, intended = template.build(tier, seed, room_id, attempt=attempt)
        report = validate(manifest, intended)
        if report.passed:
            return GeneratedInstance(
                manifest=manifest,
                instance_hash=instance_hash(manifest),
                solution=report.solution,
                intended=intended,
                min_length=report.min_length,
                optimality=report.optimality,
                report=report,
                attempts=attempt + 1,
            )
        failures.append(", ".join(f"{c.id}: {c.detail}" for c in report.checks if not c.passed))
    raise GenerationError(f"no valid instance after {max_attempts} attempts: {failures[-1] if failures else ''}")


def derive_seed(secret: str, *parts: str) -> str:
    """Secret-salted seeds for sealed content (16.3, 16.4)."""
    msg = "\x1f".join(parts).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:32]


def daily_seed(secret: str, date_iso: str) -> str:
    return derive_seed(secret, "daily", date_iso)


def season_seed(secret: str, season_id: str, tier: str, index: int) -> str:
    return derive_seed(secret, "season", season_id, tier, str(index))


def load_manifest(data: str | bytes | dict[str, Any]) -> RoomManifest:
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    return RoomManifest.model_validate(data)


def manifest_json(manifest: RoomManifest) -> str:
    return json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def practice_manifest() -> RoomManifest:
    """The single fixed public Practice room. It never changes (8.4)."""
    text = resources.files("escapement_engine.rooms.data").joinpath("practice.json").read_text("utf-8")
    return load_manifest(text)


def build_practice() -> GeneratedInstance:
    return generate("practice", PRACTICE_SEED, PRACTICE_ROOM_ID)
