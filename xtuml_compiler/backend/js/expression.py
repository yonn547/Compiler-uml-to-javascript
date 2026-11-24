"""Penerjemah ekspresi action language xtUML ke ekspresi JavaScript."""

from __future__ import annotations

import json
import re

from ...utils import js_identifier


class ExpressionError(ValueError):
    pass


_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
    | (?P<number>\d+(?:\.\d+)?)
    | (?P<ident>[A-Za-z_$][A-Za-z0-9_$]*)
    | (?P<op>==|!=|<=|>=|&&|\|\||->|[+\-*/%<>!().,?:])
    | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)

_KEYWORDS = {
    "self": "this",
    "and": "&&",
    "or": "||",
    "not": "!",
    "mod": "%",
    "div": "/",
    "true": "true",
    "false": "false",
    "null": "null",
    "undefined": "undefined",
    "new": "new",
    "typeof": "typeof",
}

_OP_MAP = {"->": "=>"}


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup or "other"
        if kind == "ws":
            continue
        if kind == "other":
            raise ExpressionError(f"Karakter '{match.group()}' tidak dikenal dalam ekspresi")
        tokens.append((kind, match.group()))
    return tokens


def _js_string(raw: str) -> str:
    escapes = {
        "n": "\n", "t": "\t", "r": "\r", "\\": "\\",
        '"': '"', "'": "'", "0": "\0",
    }
    inner = raw[1:-1]
    value = re.sub(
        r"\\(.)",
        lambda m: escapes.get(m.group(1), m.group(1)),
        inner,
    )
    return json.dumps(value, ensure_ascii=False)


def _join(parts: list[str]) -> str:
    text = " ".join(parts)
    text = re.sub(r"\s+([.,)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"\.\s+", ".", text)
    text = re.sub(r"!\s+", "!", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def translate_expression(expression: str | None) -> str:
    """Terjemahkan ekspresi xtUML menjadi ekspresi JavaScript.

    Contoh: `self.age >= 18 and name != ""` -> `this.age >= 18 && name != ""`.
    """
    if expression is None or str(expression).strip() == "":
        return "undefined"
    tokens = _tokenize(str(expression))
    if not tokens:
        return "undefined"
    parts: list[str] = []
    for kind, value in tokens:
        if kind == "string":
            parts.append(_js_string(value))
        elif kind == "number":
            parts.append(value)
        elif kind == "ident":
            parts.append(_KEYWORDS.get(value, js_identifier(value)))
        elif kind == "op":
            parts.append(_OP_MAP.get(value, value))
    result = _join(parts)
    if not result:
        raise ExpressionError("Ekspresi kosong")
    return result


def check_expression(expression: str | None) -> str | None:
    """Kembalikan pesan error bila ekspresi tidak dapat diterjemahkan."""
    try:
        translate_expression(expression)
        return None
    except ExpressionError as exc:
        return str(exc)
