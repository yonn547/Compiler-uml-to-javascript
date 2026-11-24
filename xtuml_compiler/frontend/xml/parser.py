"""Frontend XML: model xtUML terstruktur maupun format object/link lama."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ...diagnostics import Diagnostics
from ...frontend.dsl.parser import DSLParser, ParseAbort
from ...ir.model import (
    AssocEnd,
    Association,
    AttributeDef,
    ClassDef,
    DataType,
    EventDef,
    Instance,
    Link,
    Model,
    Operation,
    Parameter,
    State,
    StateMachine,
    Transition,
)
from ...utils import literal_to_expr, parse_literal
from ..common import legacy_to_model


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, *names: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) in names]


def _descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [item for item in element.iter() if item is not element and _local(item.tag) == name]


def _child_text(element: ET.Element, name: str) -> str:
    for child in _children(element, name):
        return "".join(child.itertext()).strip()
    return ""


def _bool(value: str | None) -> bool:
    return str(value or "").lower() in ("1", "true", "yes")


def _parse_actions(text: str, diagnostics: Diagnostics, source: str):
    if not text.strip():
        return []
    parser = DSLParser("{\n" + text + "\n}", source=source, diagnostics=diagnostics)
    try:
        return parser.parse_action_block()
    except ParseAbort:
        return []


def parse_xml(text: str, diagnostics: Diagnostics | None = None, source: str = "<xml>") -> Model:
    diagnostics = diagnostics or Diagnostics()
    root = ET.fromstring(text)
    root_tag = _local(root.tag)

    if root_tag == "uml" or (
        _descendants(root, "object") and not _descendants(root, "class")
    ):
        return _parse_legacy(root, diagnostics, source)

    model = Model(name=root.attrib.get("name", "Model"), source_type="XML xtUML")
    domains = _descendants(root, "domain") or [root]
    for domain in domains:
        if domain is not root:
            model.name = domain.attrib.get("name", model.name)
        for datatype in _children(domain, "datatype", "data-type"):
            model.datatypes.append(
                DataType(
                    name=datatype.attrib.get("name", "Type"),
                    base=datatype.attrib.get("base", datatype.attrib.get("type", "string")),
                )
            )
        for class_element in _children(domain, "class"):
            model.classes.append(_parse_class(class_element, diagnostics, source))
        for assoc_element in _children(domain, "association"):
            model.associations.append(_parse_association(assoc_element))
        for instance_element in _children(domain, "instance"):
            model.instances.append(_parse_instance(instance_element))
        for link_element in _children(domain, "link"):
            model.links.append(_parse_link(link_element))
    return model


def _parse_class(element: ET.Element, diagnostics: Diagnostics, source: str) -> ClassDef:
    class_def = ClassDef(
        name=element.attrib.get("name", "Class"),
        base=element.attrib.get("extends", element.attrib.get("base", "")),
    )
    for attribute in _children(element, "attribute"):
        class_def.attributes.append(
            AttributeDef(
                name=attribute.attrib.get("name", "attribute"),
                type=attribute.attrib.get("type", "any"),
                default=attribute.attrib.get("default", attribute.attrib.get("value", "")),
            )
        )
    for sm_element in _children(element, "state-machine", "stateMachine", "state_machine"):
        class_def.state_machines.append(_parse_state_machine(sm_element, diagnostics, source))
    for operation in _children(element, "operation", "method"):
        params = [
            Parameter(
                name=param.attrib.get("name", "arg"),
                type=param.attrib.get("type", "any"),
            )
            for param in _children(operation, "param", "parameter")
        ]
        body_text = _child_text(operation, "body") or (operation.text or "")
        class_def.operations.append(
            Operation(
                name=operation.attrib.get("name", "operation"),
                params=params,
                return_type=operation.attrib.get("return", operation.attrib.get("type", "void")),
                body=_parse_actions(body_text, diagnostics, source),
            )
        )
    return class_def


def _parse_state_machine(element: ET.Element, diagnostics: Diagnostics, source: str) -> StateMachine:
    machine = StateMachine(name=element.attrib.get("name", "lifecycle"))
    for state_element in _children(element, "state"):
        machine.states.append(
            State(
                name=state_element.attrib.get("name", "state"),
                initial=_bool(state_element.attrib.get("initial")),
                final=_bool(state_element.attrib.get("final")),
                entry=_parse_actions(_child_text(state_element, "entry"), diagnostics, source),
                exit=_parse_actions(_child_text(state_element, "exit"), diagnostics, source),
            )
        )
    for event_element in _children(element, "event"):
        machine.events.append(EventDef(name=event_element.attrib.get("name", event_element.text or "event")))
    for transition in _children(element, "transition"):
        machine.transitions.append(
            Transition(
                source=transition.attrib.get("from", ""),
                target=transition.attrib.get("to", ""),
                event=transition.attrib.get("event", ""),
                guard=transition.attrib.get("guard", transition.attrib.get("when", "")),
                body=_parse_actions(
                    _child_text(transition, "action") or (transition.text or ""),
                    diagnostics,
                    source,
                ),
            )
        )
    return machine


def _parse_association(element: ET.Element) -> Association:
    ends = _children(element, "end")
    if len(ends) < 2:
        raise ValueError("Association XML memerlukan dua <end>")
    first, second = ends[0], ends[1]
    return Association(
        name=element.attrib.get("name", "association"),
        end_a=_parse_end(first),
        end_b=_parse_end(second),
    )


def _parse_end(element: ET.Element) -> AssocEnd:
    class_name = element.attrib.get("class", element.attrib.get("className", "Object"))
    return AssocEnd(
        class_name=class_name,
        role=element.attrib.get("role", class_name.lower()),
        multiplicity=element.attrib.get("multiplicity", element.attrib.get("mult", "1")),
    )


def _parse_instance(element: ET.Element) -> Instance:
    values: dict[str, object] = {}
    for attribute in _children(element, "attribute"):
        name = attribute.attrib.get("name", "attribute")
        raw = attribute.attrib.get("value")
        if raw is None:
            raw = "".join(attribute.itertext()).strip()
        values[name] = literal_to_expr(parse_literal(raw))
    return Instance(
        name=element.attrib.get("name", "obj"),
        class_name=element.attrib.get("class", element.attrib.get("className", "Object")),
        values=values,
    )


def _parse_link(element: ET.Element) -> Link:
    return Link(
        association=element.attrib.get("association", element.attrib.get("relation", "link")),
        source=element.attrib.get("source", element.attrib.get("from", "")),
        target=element.attrib.get("target", element.attrib.get("to", "")),
    )


def _parse_legacy(root: ET.Element, diagnostics: Diagnostics, source: str) -> Model:
    id_map: dict[str, str] = {}
    objects: list[dict[str, object]] = []
    for obj in _descendants(root, "object"):
        obj_id = obj.attrib.get("id", "")
        name = obj.attrib.get("name", "obj")
        if obj_id:
            id_map[obj_id] = name
        attributes = {
            attribute.attrib.get("name", "attribute"): parse_literal(
                "".join(attribute.itertext()).strip()
            )
            for attribute in _children(obj, "attribute")
        }
        objects.append(
            {
                "name": name,
                "className": obj.attrib.get("class", obj.attrib.get("className")),
                "attributes": attributes,
            }
        )
    links: list[dict[str, str]] = []
    for link in _descendants(root, "link"):
        source_id = link.attrib.get("source", link.attrib.get("from", ""))
        target_id = link.attrib.get("target", link.attrib.get("to", ""))
        links.append(
            {
                "from": id_map.get(source_id, source_id),
                "to": id_map.get(target_id, target_id),
                "relation": link.attrib.get("relation", link.attrib.get("association", "link")),
            }
        )
    return legacy_to_model(objects, links, "XML", diagnostics)
