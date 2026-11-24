"""Command line interface untuk xtUML Compiler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import FORMATS, __version__, compile_text, to_mermaid, to_plantuml, write_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xtumlc",
        description="Compile model xtUML menjadi JavaScript (ESM).",
    )
    parser.add_argument("--version", action="version", version=f"xtumlc {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    compile_parser = subparsers.add_parser("compile", help="compile model menjadi JavaScript")
    compile_parser.add_argument("input", help="file model (.xtuml, .json, .xml, .puml)")
    compile_parser.add_argument("-o", "--output", help="file .js atau folder untuk --project")
    compile_parser.add_argument("--format", choices=FORMATS, default="auto")
    compile_parser.add_argument("--target", choices=("node", "browser"), default="node")
    compile_parser.add_argument("--project", action="store_true", help="hasilkan multi-file ESM")
    compile_parser.add_argument("--ir", help="simpan IR kanonik ke file JSON")
    compile_parser.add_argument(
        "--diagram", help="simpan class diagram ke file (.puml atau .mmd)"
    )
    compile_parser.add_argument(
        "--diagram-format",
        choices=("auto", "plantuml", "mermaid"),
        default="auto",
        help="format class diagram (default: ikuti ekstensi file)",
    )
    compile_parser.add_argument("--quiet", action="store_true", help="sembunyikan diagnostics")

    check_parser = subparsers.add_parser("check", help="validasi model tanpa generate kode")
    check_parser.add_argument("input")
    check_parser.add_argument("--format", choices=FORMATS, default="auto")

    subparsers.add_parser("formats", help="tampilkan format yang didukung")
    return parser


def _print_diagnostics(result, quiet: bool) -> None:
    if quiet:
        return
    text = result.message
    if text:
        print(text, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "formats":
        print("Format didukung: " + ", ".join(FORMATS))
        print("Input: DSL xtUML, JSON/IR, XML xtUML, PlantUML object diagram")
        return 0
    if args.command is None:
        parser.print_help()
        return 0

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"File tidak ditemukan: {input_path}", file=sys.stderr)
        return 1
    text = input_path.read_text(encoding="utf-8")
    format_name = args.format
    target = getattr(args, "target", "node")
    result = compile_text(text, format=format_name, target=target, source=str(input_path))

    if args.command == "check":
        _print_diagnostics(result, quiet=False)
        return 0 if result.ok else 1

    if args.ir:
        Path(args.ir).write_text(result.ir_json + "\n", encoding="utf-8")

    if args.diagram:
        if result.model is None:
            print("Model tidak tersedia untuk membuat class diagram.", file=sys.stderr)
            return 1
        diagram_format = args.diagram_format
        if diagram_format == "auto":
            suffix = Path(args.diagram).suffix.lower()
            diagram_format = "mermaid" if suffix in {".mmd", ".mermaid"} else "plantuml"
        text = (
            to_mermaid(result.model)
            if diagram_format == "mermaid"
            else to_plantuml(result.model)
        )
        diagram_path = Path(args.diagram)
        diagram_path.parent.mkdir(parents=True, exist_ok=True)
        diagram_path.write_text(text, encoding="utf-8")
        if not args.quiet:
            print(f"Class diagram ({diagram_format}) ditulis ke {diagram_path}")

    if not result.ok:
        _print_diagnostics(result, quiet=False)
        return 1

    _print_diagnostics(result, quiet=args.quiet)
    if args.project:
        directory = Path(args.output or (input_path.stem + "_js"))
        files = write_project(result, directory)
        if not args.quiet:
            print(f"Ditulis {len(files)} file ke {directory}")
        return 0

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.js, encoding="utf-8")
        if not args.quiet:
            print(f"Ditulis {output}")
    else:
        sys.stdout.write(result.js)
        if not result.js.endswith("\n"):
            sys.stdout.write("\n")
    return 0
