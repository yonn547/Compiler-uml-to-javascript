"""Adapter untuk format lama (object diagram) ke IR xtUML."""

from __future__ import annotations

from typing import Any

from ..diagnostics import Diagnostics
from ..ir.model import AssocEnd, Association, AttributeDef, ClassDef, Instance, Link, Model
from ..utils import literal_to_expr


def legacy_to_model(
    objects: list[dict[str, Any]],
    links: list[dict[str, Any]],
    source_type: str,
    diagnostics: Diagnostics | None = None,
) -> Model:
    """Ubah daftar object/link menjadi model dengan class, instance, association."""
    diagnostics = diagnostics or Diagnostics()
    model = Model(name="LegacyModel", source_type=source_type)
    classes: dict[str, ClassDef] = {}
    instances: dict[str, Instance] = {}

    for raw in objects:
        name = str(raw.get("name") or "obj")
        class_name = str(raw.get("className") or (name[:1].upper() + name[1:]) or "Object")
        values = {
            str(key): literal_to_expr(value)
            for key, value in dict(raw.get("attributes") or {}).items()
        }
        if name in instances:
            diagnostics.error(f"Instance '{name}' duplikat", source_type)
            continue
        instance = Instance(name=name, class_name=class_name, values=values)
        instances[name] = instance
        model.instances.append(instance)
        if class_name not in classes:
            classes[class_name] = ClassDef(name=class_name)
            model.classes.append(classes[class_name])
        known = {attribute.name for attribute in classes[class_name].attributes}
        for key in values:
            if key not in known:
                classes[class_name].attributes.append(AttributeDef(name=str(key), type="any"))

    associations: dict[tuple[str, str, str], str] = {}
    for raw in links:
        source = str(raw.get("from") or raw.get("source") or "")
        target = str(raw.get("to") or raw.get("target") or "")
        relation = str(raw.get("relation") or "link")
        if source not in instances:
            diagnostics.error(f"Link '{relation}' merujuk instance '{source}' yang tidak ada", source_type)
            continue
        if target not in instances:
            diagnostics.error(f"Link '{relation}' merujuk instance '{target}' yang tidak ada", source_type)
            continue
        class_a = instances[source].class_name
        class_b = instances[target].class_name
        key = (relation, class_a, class_b)
        if key not in associations:
            associations[key] = relation
            role_b = class_b.lower() if class_a != class_b else class_b.lower() + "_target"
            model.associations.append(
                Association(
                    name=relation,
                    end_a=AssocEnd(class_name=class_a, role=class_a.lower(), multiplicity="1"),
                    end_b=AssocEnd(class_name=class_b, role=role_b, multiplicity="0..*"),
                )
            )
        model.links.append(
            Link(association=relation, source=source, target=target)
        )
    return model
