"""xtUML → JavaScript compiler.

Pipeline: source → parser → IR → validator → generator → JS/runtime.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .backend.js.emitter import CodegenError, generate_bundle, generate_project
from .backend.js.expression import ExpressionError
from .diagnostics import Diagnostics
from .diagram import build_class_diagram_layout, to_mermaid, to_plantuml
from .frontend.dsl.parser import DSLParser
from .frontend.json.parser import parse_json
from .frontend.plantuml.parser import parse_plantuml
from .frontend.xml.parser import parse_xml
from .ir.model import Model
from .simulator import Simulator
from .validator import validate


__version__ = "0.1.0"
FORMATS = ("auto", "dsl", "json", "xml", "plantuml")


@dataclass
class CompileResult:
    ok: bool
    js: str = ""
    ir_json: str = ""
    files: dict[str, str] = field(default_factory=dict)
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    source_type: str = ""
    model: Model | None = None

    @property
    def message(self) -> str:
        return self.diagnostics.format()

    @property
    def class_diagram(self) -> str:
        """Sumber class diagram PlantUML dari model hasil compile."""
        return to_plantuml(self.model) if self.model else ""

    @property
    def mermaid_diagram(self) -> str:
        """Sumber class diagram Mermaid dari model hasil compile."""
        return to_mermaid(self.model) if self.model else ""


def detect_format(text: str) -> str:
    clean = text.strip()
    if clean.startswith("{") or clean.startswith("["):
        return "json"
    if clean.startswith("<"):
        return "xml"
    if re.search(r"\bobject\s+\w+\s*\{", clean, re.IGNORECASE):
        return "plantuml"
    if re.search(r"\b(domain|class|association|state\s+machine)\b", clean, re.IGNORECASE):
        return "dsl"
    return "dsl"


def _normalize_format(value: str | None) -> str:
    name = str(value or "auto").strip().lower()
    if name.startswith("xtuml"):
        return "dsl"
    if name.startswith("json"):
        return "json"
    if name.startswith("xml"):
        return "xml"
    if name.startswith("plant"):
        return "plantuml"
    return name if name in FORMATS else "auto"


def compile_text(
    text: str,
    format: str = "auto",
    target: str = "node",
    source: str = "<input>",
) -> CompileResult:
    """Compile teks model xtUML menjadi JavaScript."""
    diagnostics = Diagnostics()
    result = CompileResult(ok=False, diagnostics=diagnostics)
    if not text or not text.strip():
        diagnostics.error("Input masih kosong", source)
        return result

    source_format = _normalize_format(format)
    if source_format == "auto":
        source_format = detect_format(text)
    if source_format not in FORMATS[1:]:
        diagnostics.error(f"Format '{format}' tidak dikenal", source)
        return result

    try:
        if source_format == "dsl":
            model = DSLParser(text, source=source, diagnostics=diagnostics).parse()
        elif source_format == "json":
            model = parse_json(text, diagnostics, source)
        elif source_format == "xml":
            model = parse_xml(text, diagnostics, source)
        else:
            model = parse_plantuml(text, diagnostics, source)
    except (ValueError, ET.ParseError, TypeError) as exc:
        diagnostics.error(f"Gagal mem-parsing {source_format.upper()}: {exc}", source)
        return result

    validate(model, diagnostics)
    result.source_type = model.source_type
    result.model = model
    try:
        result.ir_json = json.dumps(model.to_dict(), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        diagnostics.error("IR tidak dapat diserialisasi ke JSON", source)

    if diagnostics.has_errors:
        return result

    try:
        result.js = generate_bundle(model, target=target)
        result.files = generate_project(model, target=target)
    except (CodegenError, ExpressionError, ValueError) as exc:
        diagnostics.error(f"Gagal membuat kode JavaScript: {exc}", source)
        return result

    result.ok = True
    return result


def compile_uml_to_js(text: str, format: str = "auto", target: str = "node") -> tuple[bool, str]:
    """API kompatibel dengan `compiler.compile_uml_to_js`."""
    result = compile_text(text, format=format, target=target)
    return result.ok, result.js if result.ok else result.message


def write_project(result: CompileResult, directory: str | Path) -> list[str]:
    """Tulis hasil project mode ke folder, kembalikan daftar path."""
    target = Path(directory)
    written: list[str] = []
    for relative, content in result.files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))
    return written
