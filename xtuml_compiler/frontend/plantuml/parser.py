"""Frontend PlantUML: object diagram dan deklarasi class sederhana."""

from __future__ import annotations

import re

from ...diagnostics import Diagnostics
from ...ir.model import AttributeDef, ClassDef, Model
from ...utils import parse_literal
from ..common import legacy_to_model


OBJECT_RE = re.compile(r"object\s+(\w+)\s*\{([^}]*)\}", re.IGNORECASE | re.DOTALL)
CLASS_RE = re.compile(r"class\s+(\w+)\s*\{([^}]*)\}", re.IGNORECASE | re.DOTALL)
LINK_RE = re.compile(
    r"(\w+)\s*(-->|<--|--|\.\.>|\.\.)\s*(\w+)\s*(?::\s*([\w-]+))?", re.DOTALL
)


def _parse_attributes(block: str) -> dict[str, object]:
    attributes: dict[str, object] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip().lstrip("+-").strip()
        if not line:
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            attributes[key.strip()] = parse_literal(value.strip().strip('"\''))
        elif ":" in line:
            key, _type = line.split(":", 1)
            attributes[key.strip()] = None
    return attributes


def parse_plantuml(text: str, diagnostics: Diagnostics | None = None, source: str = "<plantuml>") -> Model:
    diagnostics = diagnostics or Diagnostics()
    objects: list[dict[str, object]] = []
    for match in OBJECT_RE.finditer(text):
        name = match.group(1)
        objects.append(
            {
                "name": name,
                "className": name[:1].upper() + name[1:],
                "attributes": _parse_attributes(match.group(2)),
            }
        )

    links: list[dict[str, str]] = []
    for match in LINK_RE.finditer(text):
        source_name, arrow, target_name, relation = match.groups()
        if arrow == "<--":
            source_name, target_name = target_name, source_name
        links.append(
            {
                "from": source_name,
                "to": target_name,
                "relation": relation or "link",
            }
        )

    model = legacy_to_model(objects, links, "PlantUML", diagnostics)
    for match in CLASS_RE.finditer(text):
        name = match.group(1)
        class_def = ClassDef(name=name)
        for attr_name in _parse_attributes(match.group(2)):
            class_def.attributes.append(AttributeDef(name=attr_name))
        existing = model.find_class(name)
        if existing:
            known = {attr.name for attr in existing.attributes}
            for attr in class_def.attributes:
                if attr.name not in known:
                    existing.attributes.append(attr)
        else:
            model.classes.append(class_def)
    return model
