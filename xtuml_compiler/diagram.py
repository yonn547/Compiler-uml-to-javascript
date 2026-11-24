"""Class diagram generator untuk IR kanonik xtUML.

Modul ini dipakai oleh GUI untuk menggambar diagram ke ``CTkCanvas`` dan oleh
CLI/API untuk mengekspor diagram ke PlantUML atau Mermaid. Tidak ada dependensi
eksternal: seluruh tata letak dihitung dari model IR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil, sqrt

from .ir.model import Model

# Konstanta tata letak juga dipakai oleh GUI saat menggambar ke canvas.
HEADER_HEIGHT = 34.0
LINE_HEIGHT = 18.0
BOX_PADDING = 10.0
MIN_WIDTH = 190.0
MARGIN = 40.0
GAP_X = 70.0
GAP_Y = 60.0


@dataclass(frozen=True)
class DiagramClass:
    """Satu kotak class pada kanvas."""

    name: str
    x: float
    y: float
    width: float
    height: float
    attributes: tuple[str, ...]
    operations: tuple[str, ...]
    stereotype: str = ""
    header_height: float = HEADER_HEIGHT


@dataclass(frozen=True)
class DiagramEdge:
    """Satu relasi antar class pada kanvas."""

    source: str
    target: str
    x1: float
    y1: float
    x2: float
    y2: float
    source_side: str
    target_side: str
    kind: str = "association"
    label: str = ""
    source_multiplicity: str = ""
    target_multiplicity: str = ""
    source_role: str = ""
    target_role: str = ""


@dataclass(frozen=True)
class DiagramLayout:
    """Hasil tata letak class diagram."""

    classes: tuple[DiagramClass, ...]
    edges: tuple[DiagramEdge, ...]
    width: float
    height: float

    @property
    def is_empty(self) -> bool:
        return not self.classes


@dataclass
class _BoxSpec:
    name: str
    attributes: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()
    stereotype: str = ""


def _attribute_text(attribute) -> str:
    text = f"{attribute.name} : {attribute.type}"
    if attribute.default:
        text += f" = {attribute.default}"
    return text


def _operation_text(operation) -> str:
    params = ", ".join(f"{param.name} : {param.type}" for param in operation.params)
    signature = f"{operation.name}({params})"
    if operation.return_type and operation.return_type != "void":
        signature += f" : {operation.return_type}"
    return signature


def collect_classes(model: Model) -> list[_BoxSpec]:
    """Kumpulkan class, datatype, dan class implisit dari instance."""
    specs: list[_BoxSpec] = []
    seen: set[str] = set()

    for class_def in model.classes:
        if class_def.name in seen:
            continue
        operations = tuple(_operation_text(op) for op in class_def.operations)
        operations += tuple(f"«state machine» {sm.name}" for sm in class_def.state_machines)
        specs.append(
            _BoxSpec(
                name=class_def.name,
                attributes=tuple(_attribute_text(attr) for attr in class_def.attributes),
                operations=operations,
            )
        )
        seen.add(class_def.name)

    for datatype in model.datatypes:
        if datatype.name in seen:
            continue
        specs.append(_BoxSpec(name=datatype.name, stereotype="«datatype»"))
        seen.add(datatype.name)

    # Model object diagram lama kadang hanya punya instance tanpa class eksplisit.
    for instance in model.instances:
        if instance.class_name in seen:
            continue
        specs.append(
            _BoxSpec(
                name=instance.class_name,
                attributes=tuple(sorted(str(key) for key in instance.values)),
            )
        )
        seen.add(instance.class_name)

    return specs


def _anchor(box: DiagramClass, other: DiagramClass) -> tuple[float, float, str]:
    """Titik pada sisi ``box`` yang paling dekat dengan ``other``."""
    center_x = box.x + box.width / 2
    center_y = box.y + box.height / 2
    other_x = other.x + other.width / 2
    other_y = other.y + other.height / 2
    delta_x = other_x - center_x
    delta_y = other_y - center_y

    if abs(delta_x) >= abs(delta_y):
        if delta_x >= 0:
            return box.x + box.width, center_y, "right"
        return box.x, center_y, "left"
    if delta_y >= 0:
        return center_x, box.y + box.height, "bottom"
    return center_x, box.y, "top"


def build_class_diagram_layout(model: Model) -> DiagramLayout:
    """Buat tata letak class diagram yang stabil dan dapat digulir."""
    specs = collect_classes(model)
    if not specs:
        return DiagramLayout(classes=(), edges=(), width=0.0, height=0.0)

    boxes: list[DiagramClass] = []
    widths: list[float] = []
    heights: list[float] = []
    for spec in specs:
        lines = [spec.name, spec.stereotype, *spec.attributes, *spec.operations]
        text_width = max((len(line) for line in lines if line), default=0)
        width = max(MIN_WIDTH, text_width * 7.4 + BOX_PADDING * 2 + 16)
        rows = max(1, len(spec.attributes) + len(spec.operations))
        height = HEADER_HEIGHT + rows * LINE_HEIGHT + BOX_PADDING
        widths.append(width)
        heights.append(height)
        boxes.append(
            DiagramClass(
                name=spec.name,
                x=0.0,
                y=0.0,
                width=width,
                height=height,
                attributes=spec.attributes,
                operations=spec.operations,
                stereotype=spec.stereotype,
            )
        )

    columns = min(3, max(1, ceil(sqrt(len(boxes)))))
    rows = ceil(len(boxes) / columns)
    cell_width = max(widths)
    cell_height = max(heights)

    positioned: list[DiagramClass] = []
    for index, box in enumerate(boxes):
        column = index % columns
        row = index // columns
        x = MARGIN + column * (cell_width + GAP_X) + (cell_width - box.width) / 2
        y = MARGIN + row * (cell_height + GAP_Y)
        positioned.append(
            DiagramClass(
                name=box.name,
                x=x,
                y=y,
                width=box.width,
                height=box.height,
                attributes=box.attributes,
                operations=box.operations,
                stereotype=box.stereotype,
                header_height=box.header_height,
            )
        )

    by_name = {box.name: box for box in positioned}
    edges: list[DiagramEdge] = []

    for association in model.associations:
        source = by_name.get(association.end_a.class_name)
        target = by_name.get(association.end_b.class_name)
        if source is None or target is None:
            continue
        if source is target:
            edges.append(
                DiagramEdge(
                    source=source.name,
                    target=target.name,
                    x1=source.x + source.width * 0.72,
                    y1=source.y + source.height,
                    x2=source.x + source.width * 0.28,
                    y2=source.y + source.height,
                    source_side="bottom",
                    target_side="bottom",
                    label=association.name,
                    # Multiplicity/role milik ujung lawan: `Customer.orders [0..*]`
                    # ditulis di dekat class Order pada diagram UML.
                    source_multiplicity=association.end_b.multiplicity,
                    target_multiplicity=association.end_a.multiplicity,
                    source_role=association.end_b.role,
                    target_role=association.end_a.role,
                )
            )
            continue
        x1, y1, source_side = _anchor(source, target)
        x2, y2, target_side = _anchor(target, source)
        edges.append(
            DiagramEdge(
                source=source.name,
                target=target.name,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                source_side=source_side,
                target_side=target_side,
                label=association.name,
                # Multiplicity/role milik ujung lawan, sesuai notasi UML.
                source_multiplicity=association.end_b.multiplicity,
                target_multiplicity=association.end_a.multiplicity,
                source_role=association.end_b.role,
                target_role=association.end_a.role,
            )
        )

    for class_def in model.classes:
        source = by_name.get(class_def.name)
        target = by_name.get(class_def.base)
        if source is None or target is None or source is target:
            continue
        x1, y1, source_side = _anchor(source, target)
        x2, y2, target_side = _anchor(target, source)
        edges.append(
            DiagramEdge(
                source=source.name,
                target=target.name,
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                source_side=source_side,
                target_side=target_side,
                kind="generalization",
            )
        )

    width = MARGIN * 2 + columns * cell_width + (columns - 1) * GAP_X
    height = MARGIN * 2 + rows * cell_height + (rows - 1) * GAP_Y + 40
    return DiagramLayout(
        classes=tuple(positioned), edges=tuple(edges), width=width, height=height
    )


def _puml_escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _puml_name(name: str) -> str:
    return name if re.fullmatch(r"\w+", name) else f'"{_puml_escape(name)}"'


def to_plantuml(model: Model, title: str | None = None) -> str:
    """Ubah model menjadi sumber diagram PlantUML."""
    lines = ["@startuml"]
    model_title = model.name if title is None else title
    if model_title:
        lines.append(f"title {_puml_escape(model_title)}")
    lines.append("skinparam classAttributeIconSize 0")

    for spec in collect_classes(model):
        stereotype = f" <<{spec.stereotype.strip('«»')}>>" if spec.stereotype else ""
        lines.append(f"class {_puml_name(spec.name)}{stereotype} {{")
        for attribute in spec.attributes:
            lines.append(f"  + {_puml_escape(attribute)}")
        if spec.attributes and spec.operations:
            lines.append("  ..")
        for operation in spec.operations:
            lines.append(f"  + {_puml_escape(operation)}")
        lines.append("}")

    for association in model.associations:
        lines.append(
            f"{_puml_name(association.end_a.class_name)} "
            f'"{_puml_escape(association.end_b.multiplicity)}" -- '
            f'"{_puml_escape(association.end_a.multiplicity)}" '
            f"{_puml_name(association.end_b.class_name)} "
            f": {_puml_escape(association.name)}"
        )

    for class_def in model.classes:
        if class_def.base:
            lines.append(
                f"{_puml_name(class_def.base)} <|-- {_puml_name(class_def.name)}"
            )

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def _mermaid_name(name: str) -> str:
    cleaned = re.sub(r"\W", "_", name).strip("_")
    return cleaned or "Unnamed"


def _mermaid_member(text: str) -> str:
    if " : " in text:
        name, type_name = text.split(" : ", 1)
        return f"+{type_name} {name}"
    return f"+{text}"


def to_mermaid(model: Model) -> str:
    """Ubah model menjadi sumber diagram Mermaid ``classDiagram``."""
    lines = ["classDiagram"]
    for spec in collect_classes(model):
        lines.append(f"  class {_mermaid_name(spec.name)} {{")
        if spec.stereotype:
            lines.append(f"    +{spec.stereotype}")
        for attribute in spec.attributes:
            lines.append(f"    {_mermaid_member(attribute)}")
        for operation in spec.operations:
            if " : " in operation:
                signature, return_type = operation.split(" : ", 1)
                lines.append(f"    +{signature} {return_type}")
            else:
                lines.append(f"    +{operation}")
        lines.append("  }")

    for association in model.associations:
        lines.append(
            f"  {_mermaid_name(association.end_a.class_name)} "
            f'"{association.end_b.multiplicity}" -- '
            f'"{association.end_a.multiplicity}" '
            f"{_mermaid_name(association.end_b.class_name)} : {association.name}"
        )
    for class_def in model.classes:
        if class_def.base:
            lines.append(
                f"  {_mermaid_name(class_def.base)} <|-- {_mermaid_name(class_def.name)}"
            )
    return "\n".join(lines) + "\n"
