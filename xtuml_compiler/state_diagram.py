"""State diagram generator untuk state machine di IR kanonik xtUML.

Modul ini dipakai GUI untuk menggambar state machine ke ``CTkCanvas`` dan oleh
CLI/API untuk mengekspor ke PlantUML atau Mermaid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil, sqrt
from pathlib import Path

from .ir.model import Model, StateMachine, Statement

STATE_HEADER_HEIGHT = 30.0
STATE_LINE_HEIGHT = 16.0
STATE_PADDING = 8.0
MIN_WIDTH = 150.0
MARGIN = 60.0
GAP_X = 80.0
GAP_Y = 60.0
LOOP_SIZE = 38.0


@dataclass(frozen=True)
class StateNode:
    """Satu state (atau pseudo-state awal) pada kanvas."""

    name: str
    x: float
    y: float
    width: float
    height: float
    entry: tuple[str, ...] = ()
    exit: tuple[str, ...] = ()
    initial: bool = False
    final: bool = False
    pseudo: bool = False


@dataclass(frozen=True)
class StateEdge:
    """Satu transisi pada kanvas."""

    source: str
    target: str
    x1: float
    y1: float
    x2: float
    y2: float
    source_side: str
    target_side: str
    label: str = ""
    kind: str = "transition"
    is_self: bool = False


@dataclass(frozen=True)
class StateDiagramLayout:
    nodes: tuple[StateNode, ...]
    edges: tuple[StateEdge, ...]
    width: float
    height: float

    @property
    def is_empty(self) -> bool:
        return not self.nodes


def collect_state_machines(model: Model) -> list[tuple[str, StateMachine]]:
    """Kumpulkan pasangan ``(nama class, state machine)`` dari model."""
    return [
        (class_def.name, state_machine)
        for class_def in model.classes
        for state_machine in class_def.state_machines
    ]


def statement_text(statement: Statement) -> str:
    """Representasi ringkas action language untuk ditampilkan di diagram."""
    expression = statement.expression
    kind = statement.kind
    if kind == "log":
        return f"log({expression})"
    if kind == "let":
        return f"let {statement.target} = {expression}"
    if kind == "assign":
        return f"{statement.target} = {expression}"
    if kind == "return":
        return f"return {expression}"
    if kind == "create":
        created = f"new {statement.class_name}()"
        return f"let {statement.target} = {created}" if statement.target else created
    if kind == "delete":
        return f"delete {expression}"
    if kind in ("link", "unlink"):
        return f"{kind}({expression}, {statement.target})"
    if kind == "generate":
        suffix = f", {statement.payload}" if statement.payload else ""
        return f"generate({expression}{suffix})"
    if kind in ("if", "while"):
        return f"{kind} ({expression})"
    return expression or kind


def _transition_label(transition) -> str:
    parts: list[str] = []
    if transition.event:
        parts.append(transition.event)
    if transition.guard:
        parts.append(f"[{transition.guard}]")
    return " ".join(parts)


def _anchor(node: StateNode, other: StateNode) -> tuple[float, float, str]:
    center_x = node.x + node.width / 2
    center_y = node.y + node.height / 2
    other_x = other.x + other.width / 2
    other_y = other.y + other.height / 2
    delta_x = other_x - center_x
    delta_y = other_y - center_y

    if abs(delta_x) >= abs(delta_y):
        if delta_x >= 0:
            return node.x + node.width, center_y, "right"
        return node.x, center_y, "left"
    if delta_y >= 0:
        return center_x, node.y + node.height, "bottom"
    return center_x, node.y, "top"


def build_state_machine_layout(state_machine: StateMachine) -> StateDiagramLayout:
    """Buat tata letak state machine yang stabil dan dapat digulir."""
    states = list(state_machine.states)
    if not states:
        return StateDiagramLayout(nodes=(), edges=(), width=0.0, height=0.0)

    # Urutkan dari initial state agar alur transisi mudah diikuti.
    by_name = {state.name: state for state in states}
    order: list[str] = []
    seen: set[str] = set()
    initial = state_machine.initial_state
    queue = [initial] if initial in by_name else []
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        order.append(name)
        for transition in state_machine.transitions:
            if transition.source == name and transition.target in by_name:
                queue.append(transition.target)
    order.extend(state.name for state in states if state.name not in seen)

    widths: dict[str, float] = {}
    heights: dict[str, float] = {}
    for name in order:
        state = by_name[name]
        actions = [statement_text(item) for item in state.entry]
        actions += [statement_text(item) for item in state.exit]
        text_width = max([len(name), *(len(action) for action in actions)], default=0)
        widths[name] = max(MIN_WIDTH, text_width * 7.2 + STATE_PADDING * 2 + 16)
        rows = max(1, len(actions))
        heights[name] = STATE_HEADER_HEIGHT + rows * STATE_LINE_HEIGHT + STATE_PADDING

    columns = min(3, max(1, ceil(sqrt(len(order)))))
    cell_width = max(widths.values())
    cell_height = max(heights.values())

    nodes: dict[str, StateNode] = {}
    for index, name in enumerate(order):
        state = by_name[name]
        column = index % columns
        row = index // columns
        x = MARGIN + column * (cell_width + GAP_X) + (cell_width - widths[name]) / 2
        y = MARGIN + row * (cell_height + GAP_Y)
        nodes[name] = StateNode(
            name=name,
            x=x,
            y=y,
            width=widths[name],
            height=heights[name],
            entry=tuple(statement_text(item) for item in state.entry),
            exit=tuple(statement_text(item) for item in state.exit),
            initial=state.initial,
            final=state.final,
        )

    edges: list[StateEdge] = []
    if initial in nodes:
        target = nodes[initial]
        pseudo_x = target.x - 52
        pseudo_y = target.y + target.height / 2
        nodes["__initial__"] = StateNode(
            name="__initial__",
            x=pseudo_x,
            y=pseudo_y - 8,
            width=16,
            height=16,
            pseudo=True,
        )
        edges.append(
            StateEdge(
                source="__initial__",
                target=initial,
                x1=pseudo_x + 16,
                y1=pseudo_y,
                x2=target.x,
                y2=pseudo_y,
                source_side="right",
                target_side="left",
                kind="initial",
            )
        )

    for transition in state_machine.transitions:
        source = nodes.get(transition.source)
        target = nodes.get(transition.target)
        if source is None or target is None or source.pseudo or target.pseudo:
            continue
        label = _transition_label(transition)
        if source is target:
            edges.append(
                StateEdge(
                    source=source.name,
                    target=target.name,
                    x1=source.x + source.width * 0.72,
                    y1=source.y + source.height,
                    x2=source.x + source.width * 0.28,
                    y2=source.y + source.height,
                    source_side="bottom",
                    target_side="bottom",
                    label=label,
                    is_self=True,
                )
            )
            continue
        x1, y1, source_side = _anchor(source, target)
        x2, y2, target_side = _anchor(target, source)
        edges.append(
            StateEdge(
                source=source.name,
                target=target.name,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                source_side=source_side,
                target_side=target_side,
                label=label,
            )
        )

    all_nodes = tuple(nodes.values())
    width = max(node.x + node.width for node in all_nodes) + MARGIN
    height = max(node.y + node.height for node in all_nodes) + MARGIN + LOOP_SIZE
    return StateDiagramLayout(nodes=all_nodes, edges=tuple(edges), width=width, height=height)


def _escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _mermaid_text(value: object) -> str:
    return str(value).replace("\n", " ").replace('"', "'").replace(";", ",")


def _plantuml_id(name: str, aliases: dict[str, str]) -> str:
    return aliases.get(name, _escape(name))


def to_plantuml_state(
    state_machine: StateMachine, class_name: str = "", title: str | None = None
) -> str:
    """Ubah satu state machine menjadi sumber diagram state PlantUML."""
    diagram_title = title
    if diagram_title is None:
        diagram_title = f"{class_name}.{state_machine.name}" if class_name else state_machine.name

    lines = ["@startuml"]
    if diagram_title:
        lines.append(f"title {_escape(diagram_title)}")
    lines.append("skinparam StateAttributeIconSize 0")

    aliases: dict[str, str] = {}
    for index, state in enumerate(state_machine.states):
        alias = f"state_{index}"
        aliases[state.name] = alias
        if state.entry or state.exit:
            lines.append(f'state "{_escape(state.name)}" as {alias} {{')
            for item in state.entry:
                lines.append(f"  entry / {_escape(statement_text(item))}")
            for item in state.exit:
                lines.append(f"  exit / {_escape(statement_text(item))}")
            lines.append("}")
        else:
            lines.append(f'state "{_escape(state.name)}" as {alias}')
        if state.final:
            lines.append(f"{alias} --> [*]")

    initial = state_machine.initial_state
    if initial in aliases:
        lines.append(f"[*] --> {aliases[initial]}")

    for transition in state_machine.transitions:
        source = _plantuml_id(transition.source, aliases)
        target = _plantuml_id(transition.target, aliases)
        label = _transition_label(transition)
        suffix = f" : {_escape(label)}" if label else ""
        lines.append(f"{source} --> {target}{suffix}")

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def _mermaid_id(name: str, aliases: dict[str, str]) -> str:
    return aliases.get(name, re.sub(r"\W", "_", name).strip("_") or "state")


def to_mermaid_state(
    state_machine: StateMachine, class_name: str = "", title: str | None = None
) -> str:
    """Ubah satu state machine menjadi sumber diagram state Mermaid."""
    lines = ["stateDiagram-v2"]
    diagram_title = title
    if diagram_title is None and class_name:
        diagram_title = f"{class_name}.{state_machine.name}"
    if diagram_title:
        lines.append(f"  %% {_mermaid_text(diagram_title)}")

    aliases: dict[str, str] = {}
    for index, state in enumerate(state_machine.states):
        alias = f"state_{index}"
        aliases[state.name] = alias
        lines.append(f'  state "{_mermaid_text(state.name)}" as {alias}')
        for item in state.entry:
            lines.append(
                f"  note right of {alias} : entry / {_mermaid_text(statement_text(item))}"
            )
        for item in state.exit:
            lines.append(
                f"  note right of {alias} : exit / {_mermaid_text(statement_text(item))}"
            )
        if state.final:
            lines.append(f"  {alias} --> [*]")

    initial = state_machine.initial_state
    if initial in aliases:
        lines.append(f"  [*] --> {aliases[initial]}")

    for transition in state_machine.transitions:
        source = _mermaid_id(transition.source, aliases)
        target = _mermaid_id(transition.target, aliases)
        label = _transition_label(transition)
        suffix = f" : {_mermaid_text(label)}" if label else ""
        lines.append(f"  {source} --> {target}{suffix}")

    return "\n".join(lines) + "\n"


def write_state_diagrams(
    model: Model,
    path: str | Path,
    format: str = "auto",
) -> list[str]:
    """Tulis semua state machine ke file terpisah dan kembalikan daftar path."""
    entries = collect_state_machines(model)
    if not entries:
        return []

    target = Path(path)
    suffix = target.suffix.lower()
    diagram_format = format.lower()
    if diagram_format == "auto":
        diagram_format = "mermaid" if suffix in {".mmd", ".mermaid"} else "plantuml"
        extension = suffix or (".mmd" if diagram_format == "mermaid" else ".puml")
    else:
        extension = ".mmd" if diagram_format == "mermaid" else ".puml"
    base = target.with_suffix("") if suffix else target
    base.parent.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for class_name, state_machine in entries:
        text = (
            to_mermaid_state(state_machine, class_name)
            if diagram_format == "mermaid"
            else to_plantuml_state(state_machine, class_name)
        )
        safe_class = re.sub(r"\W", "_", class_name).strip("_") or "Class"
        safe_state = re.sub(r"\W", "_", state_machine.name).strip("_") or "state"
        output = base.parent / f"{base.name}.{safe_class}.{safe_state}{extension}"
        output.write_text(text, encoding="utf-8")
        written.append(str(output))
    return written
