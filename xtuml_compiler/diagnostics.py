"""Diagnostics (error/warning/info) untuk seluruh pipeline compiler."""

from __future__ import annotations

from dataclasses import dataclass, field


SEVERITIES = {"error", "warning", "info"}


@dataclass
class Diagnostic:
    severity: str
    message: str
    source: str = ""
    line: int = 0
    column: int = 0

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"Severity tidak dikenal: {self.severity}")

    def __str__(self) -> str:
        location = ""
        if self.source:
            location = self.source
        if self.line:
            location = f"{location}:{self.line}" if location else str(self.line)
            if self.column:
                location += f":{self.column}"
        prefix = f"[{self.severity.upper()}]"
        return f"{prefix} {location}: {self.message}" if location else f"{prefix} {self.message}"


@dataclass
class Diagnostics:
    items: list[Diagnostic] = field(default_factory=list)

    def add(self, severity: str, message: str, source: str = "", line: int = 0, column: int = 0) -> Diagnostic:
        item = Diagnostic(severity, message, source, line, column)
        self.items.append(item)
        return item

    def error(self, message: str, source: str = "", line: int = 0, column: int = 0) -> Diagnostic:
        return self.add("error", message, source, line, column)

    def warning(self, message: str, source: str = "", line: int = 0, column: int = 0) -> Diagnostic:
        return self.add("warning", message, source, line, column)

    def info(self, message: str, source: str = "", line: int = 0, column: int = 0) -> Diagnostic:
        return self.add("info", message, source, line, column)

    def extend(self, other: "Diagnostics") -> None:
        self.items.extend(other.items)

    def of(self, severity: str) -> list[Diagnostic]:
        return [item for item in self.items if item.severity == severity]

    @property
    def errors(self) -> list[Diagnostic]:
        return self.of("error")

    @property
    def warnings(self) -> list[Diagnostic]:
        return self.of("warning")

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def format(self, limit: int = 100) -> str:
        if not self.items:
            return "Tidak ada diagnostics. Model valid."
        lines = [str(item) for item in self.items[:limit]]
        if len(self.items) > limit:
            lines.append(f"... dan {len(self.items) - limit} diagnostics lainnya.")
        return "\n".join(lines)
