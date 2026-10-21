"""Emergency Lockdown (section 8.1).

A research station has entered emergency lockdown. The player starts in the
maintenance bay. The exit needs restored power, an access card and a decoded
terminal credential.

    Inspect maintenance panel -> learn that a fuse is missing
    Find and take the replacement fuse
    Install the fuse, restoring power
    Read the terminal instructions
    Combine them with a discovered label
    Unlock the equipment locker
    Retrieve the access card
    Use the card at the exit reader
    Escape

This module is a constrained template, never free-form generation (12.1).
A seed picks placements, decoys, code values and transforms; every text comes
from deterministic templates (12.5).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..rng import SeededRandom
from ..schemas.manifest import (
    Budget,
    ClueDef,
    CodeDerivation,
    CodeLock,
    Cond,
    Effect,
    ExitDef,
    InspectVariant,
    LocationDef,
    Milestone,
    ObjectDef,
    RoomManifest,
    Rule,
    Transform,
)
from ..version import ENGINE_VERSION

FAMILY = "emergency_lockdown"
FAMILY_TITLE = "Emergency Lockdown"
TEMPLATE_VERSION = "el-1.0"


@dataclass(frozen=True)
class TierParams:
    locations: int
    decoys: int
    depth: int
    code_digits: int
    budget: int
    ranked: bool


TIERS: dict[str, TierParams] = {
    "practice": TierParams(locations=3, decoys=3, depth=1, code_digits=3, budget=60, ranked=False),
    "standard": TierParams(locations=3, decoys=8, depth=2, code_digits=4, budget=60, ranked=True),
    "hard": TierParams(locations=5, decoys=14, depth=3, code_digits=4, budget=90, ranked=True),
}

INTRO = (
    "A research station has entered emergency lockdown. You start in the maintenance bay. "
    "The exit needs restored power, an access card and a decoded terminal credential. "
    "The emergency clock advances when you take an action, not while you read."
)
GOAL_TEXT = "Escape to the exterior loading dock."

LOCATION_TEXT: dict[str, tuple[str, str]] = {
    "maintenance_bay": (
        "Maintenance bay",
        "A cramped bay of pipes and cable trays. Amber emergency strips give just enough light to work by.",
    ),
    "control_room": (
        "Control room",
        "Banks of dark monitors face a long operations desk. This is the station's nerve centre.",
    ),
    "security_vestibule": (
        "Security vestibule",
        "A narrow chamber in front of the blast door. Everything here is bolted down and labelled.",
    ),
    "storage_annex": (
        "Storage annex",
        "Floor-to-ceiling shelving and stacked crates. The air smells of dust and machine oil.",
    ),
    "server_room": (
        "Server room",
        "Rows of racks stand silent in the cold. Cable bundles run overhead like vines.",
    ),
    "exterior": (
        "Exterior loading dock",
        "Cold night air and open sky. You are outside the station.",
    ),
}

CONTAINER_TEXT: dict[str, tuple[str, str]] = {
    "tool_cabinet": ("Tool cabinet", "A steel tool cabinet with a stiff latch."),
    "parts_drawer": ("Parts drawer", "A shallow drawer labelled SPARES."),
    "supply_crate": ("Supply crate", "A plastic supply crate with a clip-down lid."),
    "desk_drawer": ("Desk drawer", "The top drawer of the operations desk."),
}

# (id, name, description, container?)
DECOYS: list[tuple[str, str, str, bool]] = [
    ("mop_bucket", "Mop bucket", "A grey mop bucket, half full of murky water.", False),
    ("wall_calendar", "Wall calendar", "A calendar still turned to last month. Nothing is written on it.", False),
    ("fire_extinguisher", "Fire extinguisher", "A wall-mounted fire extinguisher with a current inspection tag.", False),
    ("coffee_machine", "Coffee machine", "A dented coffee machine. The carafe is empty and cold.", False),
    ("pipe_manifold", "Pipe manifold", "A knot of insulated pipes. Condensation beads along the lagging.", False),
    ("swivel_chair", "Swivel chair", "A worn swivel chair with a split seat.", False),
    ("coat_hooks", "Coat hooks", "Three empty coat hooks.", False),
    ("notice_board", "Notice board", "A cork board covered in faded safety posters.", False),
    ("water_cooler", "Water cooler", "A water cooler with an empty bottle.", False),
    ("cable_reel", "Cable reel", "A heavy reel of orange cable, too bulky to move.", False),
    ("ventilation_grille", "Ventilation grille", "A wide grille. Stale air barely moves through it.", False),
    ("hard_hat_rack", "Hard hat rack", "A rack of yellow hard hats in assorted sizes.", False),
    ("laundry_cart", "Laundry cart", "A cart of folded overalls that smell of detergent.", False),
    ("whiteboard", "Whiteboard", "A whiteboard wiped clean apart from a faint grid.", False),
    ("dried_plant", "Dried plant", "An office plant that gave up some time ago.", False),
    ("safety_shower", "Safety shower", "A safety shower station tagged OUT OF SERVICE.", False),
    ("locker_bench", "Locker bench", "A long bench for changing into overalls.", False),
    ("cracked_monitor", "Cracked monitor", "A monitor with a spiderweb crack across the screen.", False),
    ("pressure_gauge", "Pressure gauge", "A wall gauge whose needle rests in the green band.", False),
    ("bench_vice", "Bench vice", "A bench vice clamped to a wall shelf.", False),
    ("storage_bin", "Storage bin", "A lidded storage bin.", True),
    ("filing_cabinet", "Filing cabinet", "A two-drawer filing cabinet.", True),
    ("first_aid_box", "First aid box", "A green first aid box mounted on the wall.", True),
    ("shipping_crate", "Shipping crate", "A wooden shipping crate with a hinged lid.", True),
]

STATE_LABELS = {"open": ("open", "closed"), "locked": ("locked", "unlocked")}

TRANSFORM_PHRASES = {
    "reverse": "read the digits in reverse order",
    "rotate_left": "move the first digit to the end",
    "swap_ends": "swap the first and last digits",
}


def apply_transforms(digits: str, transforms: list[Transform]) -> str:
    out = digits
    for t in transforms:
        if t.op == "reverse":
            out = out[::-1]
        elif t.op == "add_mod10":
            out = "".join(str((int(d) + (t.k or 0)) % 10) for d in out)
        elif t.op == "rotate_left":
            out = out[1:] + out[:1]
        elif t.op == "swap_ends":
            out = out[-1] + out[1:-1] + out[0] if len(out) > 1 else out
    return out


def _flag(name: str, value: Any = True, msg: str = "Nothing happens.") -> Cond:
    return Cond(kind="flag", name=name, value=value, fail_message=msg)


def _state(obj: str, key: str, value: Any, msg: str = "Nothing happens.") -> Cond:
    return Cond(kind="state", obj=obj, key=key, value=value, fail_message=msg)


@dataclass
class _Plan:
    """Template-side bookkeeping used to emit the intended solution."""

    graph: dict[str, list[str]] = field(default_factory=dict)
    where: dict[str, str] = field(default_factory=dict)  # object -> location (resolved)
    container_of: dict[str, str] = field(default_factory=dict)
    revealer: dict[str, str] = field(default_factory=dict)  # hidden obj -> fixture to inspect
    clue_sources: list[str] = field(default_factory=list)  # fixtures to inspect for the code
    terminal_room: str = "control_room"
    code: str = ""


def build(tier: str, seed: str, room_id: str, attempt: int = 0) -> tuple[RoomManifest, list[dict[str, Any]]]:
    """Build one instance. Returns (manifest, intended_solution_actions)."""
    params = TIERS[tier]
    rng = SeededRandom(FAMILY, TEMPLATE_VERSION, tier, seed, str(attempt))
    plan = _Plan()

    # -- locations and connections ----------------------------------------
    loc_ids = ["maintenance_bay", "control_room", "security_vestibule"]
    edges: list[tuple[str, str, list[Cond]]] = []
    power_door = [_flag("power", True, "The vestibule door is sealed. Its motor has no power.")]
    edges.append(("maintenance_bay", "control_room", []))
    edges.append(("control_room", "security_vestibule", power_door))
    if params.locations == 5:
        loc_ids += ["storage_annex", "server_room"]
        edges.append((rng.choice(["maintenance_bay", "control_room"]), "storage_annex", []))
        edges.append((rng.choice(["control_room", "storage_annex"]), "server_room", []))
    pre_power = [loc for loc in loc_ids if loc != "security_vestibule"]

    exits: dict[str, list[ExitDef]] = {loc: [] for loc in loc_ids}
    for a, b, req in edges:
        exits[a].append(ExitDef(to=b, requires=req))
        exits[b].append(ExitDef(to=a, requires=req))
        plan.graph.setdefault(a, []).append(b)
        plan.graph.setdefault(b, []).append(a)
    exits["security_vestibule"].append(ExitDef(to="exterior", requires=[_flag("exit_open", True, "The blast door is sealed.")]))
    plan.graph.setdefault("security_vestibule", []).append("exterior")

    locations = [LocationDef(id=loc, name=LOCATION_TEXT[loc][0], description=LOCATION_TEXT[loc][1], exits=exits[loc]) for loc in loc_ids]
    locations.append(LocationDef(id="exterior", name=LOCATION_TEXT["exterior"][0], description=LOCATION_TEXT["exterior"][1], terminal=True))

    # -- clue ids: stable public ids, shuffled so they reveal no ordering ----
    clue_numbers = rng.sample(list(range(10, 100)), 6)
    clue_ids = [f"clue_{n:02d}" for n in clue_numbers]
    c_panel, c_label, c_instr, c_roster, c_chart, _spare = clue_ids

    # -- placements -------------------------------------------------------
    practice = tier == "practice"
    if practice:
        cabinet_loc, fuse_mode, fuse_loc, note_loc = "maintenance_bay", "container", "control_room", "control_room"
        terminal_loc = "control_room"
    else:
        cabinet_loc = rng.choice(pre_power)
        fuse_mode = rng.choice(["container", "hidden"])
        fuse_loc = rng.choice(pre_power)
        note_loc = rng.choice(pre_power)
        terminal_loc = rng.choice(["control_room", "server_room"]) if params.locations == 5 else "control_room"
    plan.terminal_room = terminal_loc

    # -- code and transforms ----------------------------------------------
    digits = params.code_digits
    second = "reverse" if practice else rng.choice(["reverse", "rotate_left", "swap_ends"])
    shift_letters = ["A", "B", "C", "D"]
    offsets = rng.sample([1, 2, 3, 4, 5, 6, 7, 8, 9], 4)
    shift_index = rng.below(4)
    offset = offsets[shift_index]
    shift = shift_letters[shift_index]
    transforms: list[Transform] = []
    if params.depth >= 2:
        transforms.append(Transform(op="add_mod10", k=offset))
    transforms.append(Transform(op=second))  # type: ignore[arg-type]
    while True:
        label = rng.digits(digits)
        code = apply_transforms(label, transforms)
        if code != label and len(set(label)) > 1 and len(set(code)) > 1:
            break
    plan.code = code

    spaced = " ".join(label)
    phrase = TRANSFORM_PHRASES[second]
    if params.depth == 1:
        instruction = f"Equipment locker code: take the locker label and {phrase}."
    elif params.depth == 2:
        instruction = (
            "Equipment locker code: add the on-duty shift's keypad offset to each digit of the "
            f"locker label (9 wraps round to 0), then {phrase}."
        )
    else:
        instruction = (
            "Equipment locker code: look up the on-duty shift's keypad offset, add it to each digit of "
            f"the locker label (9 wraps round to 0), then {phrase}."
        )

    objects: list[ObjectDef] = []
    rules: list[Rule] = []
    clues: list[ClueDef] = [
        ClueDef(
            id=c_panel,
            text="Maintenance panel: fuse slot F3 is empty, so main power is out. The cover is held by four screws.",
            refers_to=["maintenance_panel"],
        ),
        ClueDef(id=c_label, text=f"Operations note: 'Equipment locker label: {spaced}.'", refers_to=["equipment_locker"]),
        ClueDef(id=c_instr, text=f"Terminal bulletin: '{instruction}'", refers_to=["equipment_locker"]),
    ]
    offset_clues: list[str] = []

    # Maintenance panel.
    objects.append(
        ObjectDef(
            id="maintenance_panel",
            name="Maintenance panel",
            description="A grey breaker panel stencilled MAIN POWER.",
            location="maintenance_bay",
            state={"open": False, "secured": True},
            public_state=["open"],
            operations=["open", "close"],
            open_requires=[_state("maintenance_panel", "secured", False, "The cover is held shut by four screws.")],
            inspect_variants=[
                InspectVariant(
                    when=[_flag("power", True)],
                    text="The breaker rail is complete and every lamp is green. Main power is flowing.",
                ),
                InspectVariant(
                    when=[],
                    text=(
                        "A grey breaker panel stencilled MAIN POWER. A status lamp blinks FUSE MISSING: "
                        "slot F3 is empty. The cover is held by four screws."
                    ),
                    effects=[Effect(kind="discover", clue=c_panel)],
                    reveals_information=True,
                ),
            ],
        )
    )
    # Tool cabinet and screwdriver.
    objects.append(
        ObjectDef(
            id="tool_cabinet",
            name=CONTAINER_TEXT["tool_cabinet"][0],
            description=CONTAINER_TEXT["tool_cabinet"][1],
            location=cabinet_loc,
            container=True,
            state={"open": False},
            public_state=["open"],
            operations=["open", "close"],
        )
    )
    objects.append(
        ObjectDef(
            id="screwdriver",
            name="Screwdriver",
            description="A flat-head screwdriver with a rubber grip.",
            location="tool_cabinet",
            portable=True,
        )
    )
    plan.where["tool_cabinet"] = cabinet_loc
    plan.container_of["screwdriver"] = "tool_cabinet"
    rules.append(
        Rule(
            id="unscrew_panel",
            tool="use",
            item="screwdriver",
            target="maintenance_panel",
            already=[_state("maintenance_panel", "secured", False)],
            already_message="The cover screws are already out.",
            effects=[
                Effect(kind="set_state", obj="maintenance_panel", key="secured", value=False),
                Effect(kind="set_state", obj="maintenance_panel", key="open", value=True),
            ],
            message="You back out the four screws and lift the cover away. The breaker rail is exposed, with slot F3 empty.",
        )
    )

    # Replacement fuse: in a drawer, or taped somewhere and revealed by inspection.
    if fuse_mode == "container":
        drawer_id = "parts_drawer" if practice else rng.choice(["parts_drawer", "supply_crate", "desk_drawer"])
        if drawer_id == "desk_drawer":
            fuse_loc = "control_room"
        objects.append(
            ObjectDef(
                id=drawer_id,
                name=CONTAINER_TEXT[drawer_id][0],
                description=CONTAINER_TEXT[drawer_id][1],
                location=fuse_loc,
                container=True,
                state={"open": False},
                public_state=["open"],
                operations=["open", "close"],
            )
        )
        objects.append(
            ObjectDef(
                id="replacement_fuse",
                name="Replacement fuse",
                description="A ceramic cartridge fuse marked F3, 30A.",
                location=drawer_id,
                portable=True,
            )
        )
        plan.where[drawer_id] = fuse_loc
        plan.container_of["replacement_fuse"] = drawer_id
    else:
        objects.append(
            ObjectDef(
                id="workbench",
                name="Workbench",
                description="A scarred steel workbench.",
                location=fuse_loc,
                inspect_variants=[
                    InspectVariant(when=[_flag("fuse_found", True)], text="A scarred steel workbench. The tape underneath hangs loose."),
                    InspectVariant(
                        when=[],
                        text="A scarred steel workbench. Taped beneath the top you find a replacement fuse.",
                        effects=[
                            Effect(kind="reveal", obj="replacement_fuse"),
                            Effect(kind="set_flag", name="fuse_found", value=True),
                        ],
                        reveals_information=True,
                    ),
                ],
            )
        )
        objects.append(
            ObjectDef(
                id="replacement_fuse",
                name="Replacement fuse",
                description="A ceramic cartridge fuse marked F3, 30A.",
                location=fuse_loc,
                portable=True,
                hidden=True,
            )
        )
        plan.where["workbench"] = fuse_loc
        plan.where["replacement_fuse"] = fuse_loc
        plan.revealer["replacement_fuse"] = "workbench"
    rules.append(
        Rule(
            id="install_fuse",
            tool="use",
            item="replacement_fuse",
            target="maintenance_panel",
            already=[_flag("power", True)],
            already_message="Main power is already restored.",
            requires=[_state("maintenance_panel", "open", True, "The panel cover is closed.")],
            effects=[
                Effect(kind="move_object", obj="replacement_fuse", to="@gone"),
                Effect(kind="set_flag", name="power", value=True),
            ],
            message="You seat the fuse in slot F3. Relays clack, the strip lights steady and the station hums: main power restored.",
        )
    )

    # Operations note with the locker label.
    objects.append(
        ObjectDef(
            id="operations_note",
            name="Operations note",
            description="A printed operations note.",
            location=note_loc,
            portable=True,
            inspect_variants=[
                InspectVariant(
                    when=[],
                    text=f"A printed operations note, mostly routine. A line at the bottom reads: 'Equipment locker label: {spaced}.'",
                    effects=[Effect(kind="discover", clue=c_label)],
                    reveals_information=True,
                )
            ],
        )
    )
    plan.where["operations_note"] = note_loc
    plan.clue_sources.append("operations_note")

    # Offset clues for deeper tiers.
    if params.depth >= 2:
        roster_loc = rng.choice(pre_power)
        if params.depth == 2:
            roster_text = f"Duty roster: tonight's shift is {shift}, keypad offset +{offset}."
        else:
            roster_text = f"Duty roster: tonight's shift is {shift}."
        clues.append(ClueDef(id=c_roster, text=roster_text, refers_to=["equipment_locker"]))
        offset_clues.append(c_roster)
        objects.append(
            ObjectDef(
                id="duty_roster",
                name="Duty roster",
                description="A clipboard of shift assignments.",
                location=roster_loc,
                inspect_variants=[
                    InspectVariant(
                        when=[],
                        text=f"A clipboard of shift assignments. The top sheet says: '{roster_text.split(': ', 1)[1]}'",
                        effects=[Effect(kind="discover", clue=c_roster)],
                        reveals_information=True,
                    )
                ],
            )
        )
        plan.where["duty_roster"] = roster_loc
        plan.clue_sources.append("duty_roster")
    if params.depth >= 3:
        chart_loc = rng.choice([loc for loc in ("storage_annex", "server_room") if loc in loc_ids])
        table = ", ".join(f"{s} +{o}" for s, o in zip(shift_letters, offsets))
        chart_text = f"Keypad offsets by shift: {table}."
        clues.append(ClueDef(id=c_chart, text=chart_text, refers_to=["equipment_locker"]))
        offset_clues.append(c_chart)
        objects.append(
            ObjectDef(
                id="calibration_chart",
                name="Calibration chart",
                description="A laminated chart pinned to the wall.",
                location=chart_loc,
                inspect_variants=[
                    InspectVariant(
                        when=[],
                        text=f"A laminated chart pinned to the wall. It lists keypad offsets by shift: {table}.",
                        effects=[Effect(kind="discover", clue=c_chart)],
                        reveals_information=True,
                    )
                ],
            )
        )
        plan.where["calibration_chart"] = chart_loc
        plan.clue_sources.append("calibration_chart")

    # Terminal.
    objects.append(
        ObjectDef(
            id="operations_terminal",
            name="Operations terminal",
            description="A wall terminal for station operations.",
            location=terminal_loc,
            inspect_variants=[
                InspectVariant(
                    when=[_flag("power", True)],
                    text=f"The terminal has woken up. A security bulletin fills the screen: '{instruction}'",
                    effects=[Effect(kind="discover", clue=c_instr)],
                    reveals_information=True,
                ),
                InspectVariant(when=[], text="The terminal's screen is dark. It needs main power."),
            ],
        )
    )
    plan.where["operations_terminal"] = terminal_loc

    # Equipment locker, access card, exit reader.
    derivation = CodeDerivation(
        base_digits=label,
        base_clue=c_label,
        offset_clues=offset_clues,
        instruction_clue=c_instr,
        transforms=transforms,
    )
    objects.append(
        ObjectDef(
            id="equipment_locker",
            name="Equipment locker",
            description="A tall steel locker with a numeric keypad.",
            location="security_vestibule",
            container=True,
            state={"open": False, "locked": True},
            public_state=["open", "locked"],
            operations=["open", "close", "enter_code"],
            code_lock=CodeLock(
                code=code,
                requires=[_flag("power", True, "The keypad is dark.")],
                derivation=derivation,
            ),
            inspect_variants=[
                InspectVariant(
                    when=[],
                    text=f"A tall steel locker with a numeric keypad. A worn sticker on the door says LABEL: SEE OPERATIONS NOTE. The keypad takes {digits} digits.",
                )
            ],
        )
    )
    objects.append(
        ObjectDef(
            id="access_card",
            name="Access card",
            description="A security access card on a lanyard.",
            location="equipment_locker",
            portable=True,
        )
    )
    plan.where["equipment_locker"] = "security_vestibule"
    plan.container_of["access_card"] = "equipment_locker"
    objects.append(
        ObjectDef(
            id="exit_reader",
            name="Exit reader",
            description="A card reader beside the blast door. Its display reads PRESENT AUTHORISED CARD.",
            location="security_vestibule",
        )
    )
    plan.where["exit_reader"] = "security_vestibule"
    rules.append(
        Rule(
            id="open_blast_door",
            tool="use",
            item="access_card",
            target="exit_reader",
            already=[_flag("exit_open", True)],
            already_message="The blast door is already open.",
            requires=[_flag("power", True, "The reader is dark.")],
            effects=[Effect(kind="set_flag", name="exit_open", value=True)],
            message="The reader chirps green. With a groan, the blast door rolls up onto the loading dock.",
        )
    )

    # -- decoys -----------------------------------------------------------
    used_ids = {o.id for o in objects}
    pool = [d for d in DECOYS if d[0] not in used_ids]
    if practice:
        picks = [d for d in pool if d[0] in ("mop_bucket", "wall_calendar", "fire_extinguisher")]
        spots = {"mop_bucket": "maintenance_bay", "wall_calendar": "control_room", "fire_extinguisher": "security_vestibule"}
    else:
        picks = rng.sample(pool, params.decoys)
        spots = {d[0]: rng.choice(loc_ids) for d in picks}
    for did, name, desc, is_container in picks:
        objects.append(
            ObjectDef(
                id=did,
                name=name,
                description=desc + (" It is empty." if is_container else ""),
                location=spots[did],
                container=is_container,
                decoy=True,
                state={"open": False} if is_container else {},
                public_state=["open"] if is_container else [],
                operations=["open", "close"] if is_container else [],
            )
        )

    # Shuffle object order within the manifest so listing order carries no meaning.
    if not practice:
        objects = rng.shuffle(objects)

    # -- milestones (private) and progressive hints for humans --------------
    code_inputs = [Cond(kind="discovered", clue=c) for c in [c_label, *offset_clues]]
    offset_hint = ""
    if params.depth == 2:
        offset_hint = " The duty roster gives the offset."
    elif params.depth == 3:
        offset_hint = " The duty roster names the shift and a chart elsewhere gives its offset."
    milestones = [
        Milestone(
            id="panel_opened",
            label="Opened the maintenance panel",
            requires=[_state("maintenance_panel", "secured", False)],
            hints=[
                "The maintenance panel's cover is screwed shut. Is there a tool nearby?",
                "Open the tool cabinet, take the screwdriver and use it on the maintenance panel.",
            ],
        ),
        Milestone(
            id="power_restored",
            label="Restored main power",
            requires=[_flag("power", True)],
            hints=[
                "The panel has an empty fuse slot. Search the rooms you can reach for a spare.",
                "Find the replacement fuse, carry it to the open maintenance panel and use it on the panel.",
            ],
        ),
        Milestone(
            id="instructions_read",
            label="Read the terminal bulletin",
            requires=[Cond(kind="discovered", clue=c_instr)],
            hints=[
                "With power back, a screen somewhere has something to say.",
                "Inspect the operations terminal.",
            ],
        ),
        Milestone(
            id="code_inputs_found",
            label="Found every fact the code needs",
            requires=code_inputs,
            hints=[
                "The bulletin mentions a locker label. Printed paperwork is worth reading." + offset_hint,
                "Inspect the operations note"
                + (", the duty roster" if params.depth >= 2 else "")
                + (" and the calibration chart" if params.depth >= 3 else "")
                + ".",
            ],
        ),
        Milestone(
            id="locker_unlocked",
            label="Unlocked the equipment locker",
            requires=[_state("equipment_locker", "locked", False)],
            hints=[
                "Work the code out from your journal, then try the locker's keypad.",
                "Apply the bulletin's steps to the label digits, then interact with the equipment locker using enter_code.",
            ],
        ),
        Milestone(
            id="card_taken",
            label="Took the access card",
            requires=[Cond(kind="has", item="access_card")],
            hints=["The locker is unlocked. Look inside.", "Open the equipment locker and take the access card."],
        ),
        Milestone(
            id="exit_opened",
            label="Opened the blast door",
            requires=[_flag("exit_open", True)],
            hints=["A card reader guards the blast door.", "Use the access card on the exit reader."],
        ),
        Milestone(
            id="escaped",
            label="Escaped",
            requires=[Cond(kind="at", location="exterior")],
            hints=["The way out is open.", "Move to the exterior loading dock."],
        ),
    ]

    tier_title = {"practice": "Practice", "standard": "Standard", "hard": "Hard"}[tier]
    manifest = RoomManifest(
        room_id=room_id,
        title=f"{FAMILY_TITLE} · {tier_title}",
        family=FAMILY,
        template_version=TEMPLATE_VERSION,
        engine_version=ENGINE_VERSION,
        tier=tier,  # type: ignore[arg-type]
        seed=seed if attempt == 0 else f"{seed}#{attempt}",
        intro=INTRO,
        goal_text=GOAL_TEXT,
        budget=Budget(actions=params.budget),
        start="maintenance_bay",
        flags={"power": False, "exit_open": False, "fuse_found": False},
        state_labels=STATE_LABELS,
        locations=locations,
        objects=objects,
        rules=rules,
        clues=clues,
        milestones=milestones,
        goal=[Cond(kind="at", location="exterior")],
    )
    return manifest, _intended_solution(plan, params)


def _path(graph: dict[str, list[str]], src: str, dst: str) -> list[str]:
    prev: dict[str, str | None] = {src: None}
    queue = deque([src])
    while queue:
        here = queue.popleft()
        if here == dst:
            break
        for nxt in graph.get(here, []):
            if nxt not in prev:
                prev[nxt] = here
                queue.append(nxt)
    out = []
    node: str | None = dst
    while node is not None and node != src:
        out.append(node)
        node = prev[node]
    return list(reversed(out))


def _intended_solution(plan: _Plan, params: TierParams) -> list[dict[str, Any]]:
    """The designer's route, used for replay and shortcut comparison (12.2 #7)."""
    actions: list[dict[str, Any]] = []
    here = ["maintenance_bay"]
    opened: set[str] = set()

    def act(tool: str, **arguments: str) -> None:
        actions.append({"tool": tool, "arguments": arguments})

    def go(dst: str) -> None:
        for step in _path(plan.graph, here[0], dst):
            act("move", destination_id=step)
        here[0] = dst

    def location_of(oid: str) -> str:
        if oid in plan.container_of:
            return plan.where[plan.container_of[oid]]
        return plan.where[oid]

    def fetch(oid: str) -> None:
        go(location_of(oid))
        if oid in plan.container_of and plan.container_of[oid] not in opened:
            act("interact", target_id=plan.container_of[oid], operation="open")
            opened.add(plan.container_of[oid])
        if oid in plan.revealer:
            act("inspect", target_id=plan.revealer[oid])
        act("take", item_id=oid)

    fetch("screwdriver")
    go("maintenance_bay")
    act("use", item_id="screwdriver", target_id="maintenance_panel")
    fetch("replacement_fuse")
    for source in plan.clue_sources:
        go(plan.where[source])
        act("inspect", target_id=source)
    go("maintenance_bay")
    act("use", item_id="replacement_fuse", target_id="maintenance_panel")
    go(plan.terminal_room)
    act("inspect", target_id="operations_terminal")
    go("security_vestibule")
    act("interact", target_id="equipment_locker", operation="enter_code", value=plan.code)
    act("interact", target_id="equipment_locker", operation="open")
    act("take", item_id="access_card")
    act("use", item_id="access_card", target_id="exit_reader")
    act("move", destination_id="exterior")
    return actions
