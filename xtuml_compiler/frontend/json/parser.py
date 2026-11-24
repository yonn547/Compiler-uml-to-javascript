"""Frontend JSON: canonical IR atau format object/link lama."""

from __future__ import annotations

import json

from ...diagnostics import Diagnostics
from ...ir.model import Model
from ..common import legacy_to_model


def parse_json(text: str, diagnostics: Diagnostics | None = None, source: str = "<json>") -> Model:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("JSON root harus berupa object")
    if data.get("kind") == "xtuml-model" or "classes" in data:
        return Model.from_dict(data)
    if "objects" in data or "links" in data:
        return legacy_to_model(
            list(data.get("objects") or []),
            list(data.get("links") or []),
            "JSON",
            diagnostics,
        )
    raise ValueError("JSON tidak dikenal: gunakan 'classes' atau 'objects'")
