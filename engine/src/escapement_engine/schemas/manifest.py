"""Room manifest: the private, declarative definition of one room instance.

The engine interprets a manifest; prose never defines executable rules
(section 12.5). Every state-changing action declares preconditions, effects,
cost, the public result, the failure result and whether it reveals
information (section 9.3).
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..version import MANIFEST_FORMAT

FailureCode = Literal[
    "UNKNOWN_TARGET",
    "NOT_VISIBLE",
    "NOT_REACHABLE",
    "MISSING_ITEM",
    "PRECONDITION_NOT_MET",
    "INVALID_OPERATION",
    "INVALID_ARGUMENT",
    "ALREADY_COMPLETED",
    "EPISODE_FINISHED",
]

FAILURE_CODES: tuple[str, ...] = FailureCode.__args__  # type: ignore[attr-defined]

Operation = Literal["open", "close", "activate", "enter_code"]
OPERATIONS: tuple[str, ...] = Operation.__args__  # type: ignore[attr-defined]

Scalar = Union[bool, int, str]

INVENTORY = "@inv"
GONE = "@gone"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Cond(_Strict):
    """A predicate over private state, with the public failure it produces."""

    kind: Literal["flag", "state", "has", "at", "discovered"]
    name: str | None = None  # flag name
    obj: str | None = None  # object for `state`
    key: str | None = None  # state key for `state`
    value: Scalar = True
    item: str | None = None  # for `has`
    location: str | None = None  # for `at`
    clue: str | None = None  # for `discovered`
    fail_code: FailureCode = "PRECONDITION_NOT_MET"
    fail_message: str = "Nothing happens."

    @model_validator(mode="after")
    def _fields(self) -> Cond:
        need = {
            "flag": ("name",),
            "state": ("obj", "key"),
            "has": ("item",),
            "at": ("location",),
            "discovered": ("clue",),
        }[self.kind]
        for field in need:
            if getattr(self, field) is None:
                raise ValueError(f"cond kind {self.kind} requires {field}")
        return self


class Effect(_Strict):
    kind: Literal["set_flag", "set_state", "move_object", "reveal", "discover"]
    name: str | None = None
    value: Scalar = True
    obj: str | None = None
    key: str | None = None
    to: str | None = None
    clue: str | None = None

    @model_validator(mode="after")
    def _fields(self) -> Effect:
        need = {
            "set_flag": ("name",),
            "set_state": ("obj", "key"),
            "move_object": ("obj", "to"),
            "reveal": ("obj",),
            "discover": ("clue",),
        }[self.kind]
        for field in need:
            if getattr(self, field) is None:
                raise ValueError(f"effect kind {self.kind} requires {field}")
        return self


class InspectVariant(_Strict):
    when: list[Cond] = Field(default_factory=list)
    text: str
    effects: list[Effect] = Field(default_factory=list)
    reveals_information: bool = False


class Transform(_Strict):
    """One step in deriving a code from discovered facts."""

    op: Literal["reverse", "add_mod10", "rotate_left", "swap_ends"]
    k: int | None = None


class CodeDerivation(_Strict):
    """Private record of how a code follows from discoverable clues (12.2 #6)."""

    base_digits: str
    base_clue: str
    offset_clues: list[str] = Field(default_factory=list)
    instruction_clue: str
    transforms: list[Transform]


class CodeLock(_Strict):
    code: str
    requires: list[Cond] = Field(default_factory=list)
    on_unlock: list[Effect] = Field(default_factory=list)
    derivation: CodeDerivation


class ObjectDef(_Strict):
    id: str
    name: str
    description: str
    location: str  # a location id or a container object id
    portable: bool = False
    hidden: bool = False
    container: bool = False
    decoy: bool = False
    state: dict[str, Scalar] = Field(default_factory=dict)
    public_state: list[str] = Field(default_factory=list)
    operations: list[Operation] = Field(default_factory=list)
    open_requires: list[Cond] = Field(default_factory=list)
    code_lock: CodeLock | None = None
    inspect_variants: list[InspectVariant] = Field(default_factory=list)


class Rule(_Strict):
    """A `use` or `interact activate` behaviour."""

    id: str
    tool: Literal["use", "interact"]
    target: str
    item: str | None = None
    operation: Operation | None = None
    already: list[Cond] = Field(default_factory=list)
    already_message: str = "That has already been done."
    requires: list[Cond] = Field(default_factory=list)
    effects: list[Effect] = Field(default_factory=list)
    message: str
    cost: int = 1
    reveals_information: bool = False


class ExitDef(_Strict):
    to: str
    requires: list[Cond] = Field(default_factory=list)


class LocationDef(_Strict):
    id: str
    name: str
    description: str
    exits: list[ExitDef] = Field(default_factory=list)
    terminal: bool = False  # the goal location outside the station


class ClueDef(_Strict):
    id: str
    text: str
    refers_to: list[str] = Field(default_factory=list)


class Milestone(_Strict):
    """Private progress markers for Trace Clinic and human hints (11.5, 17.5)."""

    id: str
    label: str
    requires: list[Cond]
    required: bool = True
    hints: list[str] = Field(default_factory=list)


class Budget(_Strict):
    actions: int
    malformed: int = 3
    wrong_code_free_attempts: int = 3
    wrong_code_penalty: int = 2


StateLabel = tuple[str, str]


class RoomManifest(_Strict):
    format: Literal["escapement-manifest/1"] = MANIFEST_FORMAT  # type: ignore[assignment]
    room_id: str
    title: str
    family: str
    template_version: str
    engine_version: str
    tier: Literal["practice", "standard", "hard"]
    seed: str
    intro: str
    goal_text: str
    budget: Budget
    start: str
    flags: dict[str, Scalar] = Field(default_factory=dict)
    state_labels: dict[str, StateLabel] = Field(default_factory=dict)
    locations: list[LocationDef]
    objects: list[ObjectDef]
    rules: list[Rule] = Field(default_factory=list)
    clues: list[ClueDef] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)
    goal: list[Cond]
