"""Lexer untuk DSL xtUML berbasis teks."""

from __future__ import annotations

from dataclasses import dataclass

from ...diagnostics import Diagnostics


@dataclass
class Token:
    type: str
    value: str
    line: int
    column: int

    def __str__(self) -> str:  # pragma: no cover - helper debugging
        return f"{self.type}({self.value}) @{self.line}:{self.column}"


TWO_CHAR_OPS = {"->", "<=", ">=", "==", "!=", "&&", "||", "::"}
ONE_CHAR_OPS = set("{}()[]:,.;=+-*/%<>!?")


class Lexer:
    def __init__(self, text: str, source: str = "<input>", diagnostics: Diagnostics | None = None):
        self.text = text
        self.source = source
        self.diagnostics = diagnostics or Diagnostics()
        self.pos = 0
        self.line = 1
        self.column = 1

    def _advance(self) -> str:
        char = self.text[self.pos]
        self.pos += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            line, column = self.line, self.column

            if char in " \t\r":
                self._advance()
                continue

            if char == "\n":
                tokens.append(Token("NEWLINE", "\n", line, column))
                self._advance()
                continue

            if char == "#" or (char == "/" and self.pos + 1 < len(self.text) and self.text[self.pos + 1] == "/"):
                while self.pos < len(self.text) and self.text[self.pos] != "\n":
                    self._advance()
                continue

            if char in ('"', "'"):
                quote = char
                raw = char
                self._advance()
                while self.pos < len(self.text):
                    current = self.text[self.pos]
                    raw += current
                    self._advance()
                    if current == "\\" and self.pos < len(self.text):
                        raw += self.text[self.pos]
                        self._advance()
                    elif current == quote:
                        break
                else:
                    self.diagnostics.error(
                        "String tidak ditutup", self.source, line, column
                    )
                tokens.append(Token("STRING", raw, line, column))
                continue

            if char.isdigit():
                raw = ""
                while self.pos < len(self.text) and (
                    self.text[self.pos].isdigit()
                    or (
                        self.text[self.pos] == "."
                        and self.pos + 1 < len(self.text)
                        and self.text[self.pos + 1].isdigit()
                    )
                ):
                    raw += self._advance()
                tokens.append(Token("NUMBER", raw, line, column))
                continue

            if char.isalpha() or char in "_$":
                raw = ""
                while self.pos < len(self.text) and (
                    self.text[self.pos].isalnum() or self.text[self.pos] in "_$"
                ):
                    raw += self._advance()
                tokens.append(Token("IDENT", raw, line, column))
                continue

            pair = self.text[self.pos : self.pos + 2]
            if pair in TWO_CHAR_OPS:
                self._advance()
                self._advance()
                tokens.append(Token("OP", pair, line, column))
                continue

            if char in ONE_CHAR_OPS:
                self._advance()
                tokens.append(Token("OP", char, line, column))
                continue

            self.diagnostics.error(
                f"Karakter '{char}' tidak dikenal dan diabaikan", self.source, line, column
            )
            self._advance()

        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens
