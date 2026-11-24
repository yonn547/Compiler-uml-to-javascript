"""Representasi antara (Intermediate Representation) model xtUML.

IR ini sengaja dibuat sederhana dan dapat diserialisasi ke JSON supaya
bisa diperiksa dengan `--emit-ir` dan dipakai ulang oleh backend lain.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Statement:
    kind: str
    expression: str = ""
    target: str = ""
    class_name: str = ""
    payload: str = ""
    body: list["Statement"] = field(default_factory=list)
    orelse: list["Statement"] = field(default_factory=list)
    line: int = 0


@dataclass
class AttributeDef:
    name: str
    type: str = "string"
    default: str = ""
    line: int = 0


@dataclass
class Parameter:
    name: str
    type: str = "any"


@dataclass
class Operation:
    name: str
    params: list[Parameter] = field(default_factory=list)
    return_type: str = "void"
    body: list[Statement] = field(default_factory=list)
    line: int = 0


@dataclass
class State:
    name: str
    initial: bool = False
    final: bool = False
    entry: list[Statement] = field(default_factory=list)
    exit: list[Statement] = field(default_factory=list)
    line: int = 0


@dataclass
class EventDef:
    name: str
    params: list[Parameter] = field(default_factory=list)
    line: int = 0


@dataclass
class Transition:
    source: str
    target: str
    event: str
    guard: str = ""
    body: list[Statement] = field(default_factory=list)
    line: int = 0


@dataclass
class StateMachine:
    name: str
    states: list[State] = field(default_factory=list)
    events: list[EventDef] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    line: int = 0

    @property
    def initial_state(self) -> str:
        for state in self.states:
            if state.initial:
                return state.name
        return self.states[0].name if self.states else ""


@dataclass
class ClassDef:
    name: str
    attributes: list[AttributeDef] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    state_machines: list[StateMachine] = field(default_factory=list)
    base: str = ""
    line: int = 0


@dataclass
class AssocEnd:
    class_name: str
    role: str
    multiplicity: str = "1"
    line: int = 0


@dataclass
class Association:
    name: str
    end_a: AssocEnd
    end_b: AssocEnd
    line: int = 0


@dataclass
class Instance:
    name: str
    class_name: str
    values: dict[str, Any] = field(default_factory=dict)
    line: int = 0


@dataclass
class Link:
    association: str
    source: str
    target: str
    line: int = 0


@dataclass
class DataType:
    name: str
    base: str = "string"


@dataclass
class Model:
    name: str
    classes: list[ClassDef] = field(default_factory=list)
    associations: list[Association] = field(default_factory=list)
    instances: list[Instance] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    datatypes: list[DataType] = field(default_factory=list)
    source_type: str = "xtUML"

    def find_class(self, name: str) -> ClassDef | None:
        for class_def in self.classes:
            if class_def.name == name:
                return class_def
        return None

    def find_instance(self, name: str) -> Instance | None:
        for instance in self.instances:
            if instance.name == name:
                return instance
        return None

    def find_association(self, name: str) -> Association | None:
        for association in self.associations:
            if association.name == name:
                return association
        return None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = "xtuml-model"
        data["version"] = 1
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Model":
        def build(key: str, factory: Any) -> list[Any]:
            return [factory(**item) for item in data.get(key, [])]

        def build_class(item: dict[str, Any]) -> ClassDef:
            item = dict(item)
            item["attributes"] = [AttributeDef(**a) for a in item.get("attributes", [])]
            item["operations"] = [
                Operation(
                    name=op.get("name", "unnamed"),
                    params=[Parameter(**p) for p in op.get("params", [])],
                    return_type=op.get("return_type", "void"),
                    body=[Statement(**s) for s in op.get("body", [])],
                    line=op.get("line", 0),
                )
                for op in item.get("operations", [])
            ]
            item["state_machines"] = [build_sm(sm) for sm in item.get("state_machines", [])]
            allowed = {"name", "attributes", "operations", "state_machines", "base", "line"}
            return ClassDef(**{k: v for k, v in item.items() if k in allowed})

        def build_state(item: dict[str, Any]) -> State:
            item = dict(item)
            item["entry"] = [Statement(**s) for s in item.get("entry", [])]
            item["exit"] = [Statement(**s) for s in item.get("exit", [])]
            allowed = {"name", "initial", "final", "entry", "exit", "line"}
            return State(**{k: v for k, v in item.items() if k in allowed})

        def build_sm(item: dict[str, Any]) -> StateMachine:
            item = dict(item)
            item["states"] = [build_state(s) for s in item.get("states", [])]
            item["events"] = [EventDef(**e) for e in item.get("events", [])]
            item["transitions"] = [
                Transition(
                    source=t.get("source", ""),
                    target=t.get("target", ""),
                    event=t.get("event", ""),
                    guard=t.get("guard", ""),
                    body=[Statement(**s) for s in t.get("body", [])],
                    line=t.get("line", 0),
                )
                for t in item.get("transitions", [])
            ]
            allowed = {"name", "states", "events", "transitions", "line"}
            return StateMachine(**{k: v for k, v in item.items() if k in allowed})

        def build_assoc(item: dict[str, Any]) -> Association:
            return Association(
                name=item.get("name", "association"),
                end_a=AssocEnd(**item.get("end_a", {"class_name": "Object", "role": "objects"})),
                end_b=AssocEnd(**item.get("end_b", {"class_name": "Object", "role": "objects"})),
                line=item.get("line", 0),
            )

        def build_instance(item: dict[str, Any]) -> Instance:
            return Instance(
                name=item.get("name", "obj"),
                class_name=item.get("class_name", item.get("className", "Object")),
                values=dict(item.get("values", {})),
                line=item.get("line", 0),
            )

        return cls(
            name=data.get("name", "Model"),
            classes=[build_class(item) for item in data.get("classes", [])],
            associations=[build_assoc(item) for item in data.get("associations", [])],
            instances=[build_instance(item) for item in data.get("instances", [])],
            links=[Link(**item) for item in data.get("links", [])],
            datatypes=[DataType(**item) for item in data.get("datatypes", [])],
            source_type=data.get("source_type", "xtUML"),
        )
