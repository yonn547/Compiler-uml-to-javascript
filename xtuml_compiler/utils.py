"""Fungsi kecil yang dipakai lintas frontend/backend."""

from __future__ import annotations

import json
import re
from typing import Any


JS_RESERVED = {
    "break", "case", "catch", "class", "const", "continue", "debugger", "default",
    "delete", "do", "else", "export", "extends", "finally", "for", "function",
    "if", "import", "in", "instanceof", "let", "new", "return", "super", "switch",
    "this", "throw", "try", "typeof", "var", "void", "while", "with", "yield",
    "await", "async", "enum", "implements", "interface", "package", "private",
    "protected", "public", "static", "null", "true", "false",
}

_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def is_js_identifier(name: Any) -> bool:
    text = str(name or "")
    return bool(_IDENT_RE.match(text)) and text not in JS_RESERVED


def js_identifier(name: Any, fallback: str = "Item") -> str:
    """Ubah nama model menjadi identifier JavaScript yang valid dan deterministik."""
    text = re.sub(r"\W", "_", str(name or ""), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = "_" + text
    if text in JS_RESERVED:
        text = "_" + text
    return text


def normalize_multiplicity(value: Any) -> str:
    text = str(value if value is not None else "1").strip()
    if not text:
        return "1"
    return text


def parse_multiplicity(value: Any) -> tuple[int, float, bool] | None:
    """Kembalikan (min, max, many). max=inf berarti tidak terbatas."""
    text = normalize_multiplicity(value)
    if text == "*":
        return 0, float("inf"), True
    if ".." in text:
        low, high = (part.strip() for part in text.split("..", 1))
        if low not in ("0", "1") and not low.isdigit():
            return None
        if high != "*" and not high.isdigit():
            return None
        minimum = int(low)
        maximum = float("inf") if high == "*" else int(high)
        if maximum < minimum:
            return None
        return minimum, maximum, maximum != 1
    if text.isdigit():
        number = int(text)
        return number, number, number > 1
    return None


def is_multiplicity_valid(value: Any) -> bool:
    return parse_multiplicity(value) is not None


def parse_literal(value: Any) -> Any:
    """Konversi teks nilai atribut menjadi Python literal bila memungkinkan."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "none"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def literal_to_expr(value: Any) -> str:
    """Rubah nilai Python menjadi ekspresi literal JavaScript."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        items = ", ".join(f"{json.dumps(str(k))}: {literal_to_expr(v)}" for k, v in value.items())
        return "{ " + items + " }"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(literal_to_expr(item) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def slugify(name: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(name or "xtuml").lower()).strip("-")
    return text or "xtuml"
