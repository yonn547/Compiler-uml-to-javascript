import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xtuml_compiler import (  # noqa: E402
    build_class_diagram_layout,
    cardinality_from_multiplicities,
    cardinality_label,
    compile_text,
    to_mermaid,
    to_plantuml,
)
from xtuml_compiler.ir.model import AssocEnd, Association  # noqa: E402


DSL_MODEL = ROOT / "examples" / "shop.xtuml"


class DiagramTests(unittest.TestCase):
    def setUp(self):
        self.result = compile_text(DSL_MODEL.read_text(encoding="utf-8"), format="dsl")
        self.assertTrue(self.result.ok, self.result.message)

    def test_plantuml_from_compile_result(self):
        puml = to_plantuml(self.result.model)
        self.assertEqual(self.result.class_diagram, puml)
        self.assertIn("@startuml", puml)
        self.assertIn("title Shop", puml)
        self.assertIn("class Customer {", puml)
        self.assertIn("+ id : string", puml)
        self.assertIn("+ label() : string", puml)
        self.assertIn("«state machine» lifecycle", puml)
        self.assertIn("class Money <<datatype>>", puml)
        # `Customer.orders [0..*]` ditaruh di dekat class Order.
        self.assertIn('Customer "1" -- "0..*" Order : placedOrder [1:N]', puml)
        self.assertIn("@enduml", puml)

    def test_mermaid_from_compile_result(self):
        mermaid = to_mermaid(self.result.model)
        self.assertEqual(self.result.mermaid_diagram, mermaid)
        self.assertTrue(mermaid.startswith("classDiagram"))
        self.assertIn("+string name", mermaid)
        self.assertIn("+label() string", mermaid)
        self.assertIn('Customer "1" -- "0..*" Order : placedOrder [1:N]', mermaid)

    def test_layout(self):
        layout = build_class_diagram_layout(self.result.model)
        self.assertFalse(layout.is_empty)
        self.assertEqual(
            {box.name for box in layout.classes},
            {"Customer", "Order", "Money"},
        )
        self.assertEqual(len(layout.edges), 1)
        edge = layout.edges[0]
        self.assertEqual((edge.source, edge.target), ("Customer", "Order"))
        self.assertEqual(edge.source_multiplicity, "1")
        self.assertEqual(edge.target_multiplicity, "0..*")
        self.assertEqual(edge.cardinality, "1:N")
        self.assertTrue(edge.source_side)
        self.assertTrue(edge.target_side)
        self.assertGreater(layout.width, 0)
        self.assertGreater(layout.height, 0)

        for first_index, first in enumerate(layout.classes):
            for second in layout.classes[first_index + 1 :]:
                overlaps = (
                    first.x < second.x + second.width
                    and second.x < first.x + first.width
                    and first.y < second.y + second.height
                    and second.y < first.y + first.height
                )
                self.assertFalse(overlaps, f"{first.name} bertabrakan dengan {second.name}")

    def test_cardinality_from_multiplicities(self):
        cases = (
            ("1", "1", "1:1"),
            ("1", "0..*", "1:N"),
            ("0..*", "1", "N:1"),
            ("0..*", "0..*", "N:M"),
            ("0..1", "0..1", "1:1"),
            ("2..5", "1", "N:1"),
            ("1..*", "*", "N:M"),
            ("", "1", "1:1"),
        )
        for source, target, expected in cases:
            with self.subTest(source=source, target=target):
                self.assertEqual(
                    cardinality_from_multiplicities(source, target), expected
                )

    def test_cardinality_label_uses_opposite_end(self):
        association = Association(
            "menaungi",
            AssocEnd("Dosen", "mahasiswa", "0..*"),
            AssocEnd("Mahasiswa", "dosen", "1"),
        )
        # Role di Dosen.mahasiswa menentukan multiplicity di ujung Mahasiswa.
        self.assertEqual(cardinality_label(association), "1:N")

        many_to_many = Association(
            "mengajar",
            AssocEnd("Dosen", "mataKuliah", "0..*"),
            AssocEnd("MataKuliah", "dosen", "1..*"),
        )
        self.assertEqual(cardinality_label(many_to_many), "N:M")

    def test_inheritance_diagram(self):
        source = """
        domain Demo {
          class Person { attribute name : string }
          class Student extends Person { attribute nim : string }
        }
        """
        result = compile_text(source, format="dsl")
        self.assertTrue(result.ok, result.message)
        self.assertIn("Person <|-- Student", to_plantuml(result.model))
        self.assertIn("Person <|-- Student", to_mermaid(result.model))

        layout = build_class_diagram_layout(result.model)
        generalizations = [edge for edge in layout.edges if edge.kind == "generalization"]
        self.assertEqual(len(generalizations), 1)
        self.assertEqual(
            (generalizations[0].source, generalizations[0].target), ("Student", "Person")
        )

    def test_cli_diagram_export(self):
        with tempfile.TemporaryDirectory() as directory:
            puml_path = Path(directory) / "shop.puml"
            output = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "xtuml_compiler",
                    "compile",
                    str(DSL_MODEL),
                    "--diagram",
                    str(puml_path),
                    "--quiet",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(output.returncode, 0, output.stderr)
            self.assertIn("@startuml", puml_path.read_text(encoding="utf-8"))
            self.assertIn("placedOrder [1:N]", puml_path.read_text(encoding="utf-8"))

            mmd_path = Path(directory) / "shop.mmd"
            output = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "xtuml_compiler",
                    "compile",
                    str(DSL_MODEL),
                    "--diagram",
                    str(mmd_path),
                    "--quiet",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(output.returncode, 0, output.stderr)
            self.assertTrue(
                mmd_path.read_text(encoding="utf-8").startswith("classDiagram")
            )
            self.assertIn("placedOrder [1:N]", mmd_path.read_text(encoding="utf-8"))

    def test_gui_cardinality_badge(self):
        try:
            import app  # noqa: PLC0415
        except ImportError as exc:
            self.skipTest(f"customtkinter tidak tersedia: {exc}")

        class FakeCanvas:
            def __init__(self):
                self.items = []

            def delete(self, *_args):
                self.items.clear()

            def create_text(self, *args, **kwargs):
                self.items.append(("text", args, kwargs))
                return len(self.items)

            def create_rectangle(self, *args, **kwargs):
                self.items.append(("rect", args, kwargs))
                return len(self.items)

            def create_line(self, *args, **kwargs):
                self.items.append(("line", args, kwargs))
                return len(self.items)

            def create_polygon(self, *args, **kwargs):
                self.items.append(("poly", args, kwargs))
                return len(self.items)

            def configure(self, **kwargs):
                self.config = kwargs

            def winfo_width(self):
                return 600

            def winfo_height(self):
                return 400

        class FakeWidget:
            def configure(self, **kwargs):
                self.config = kwargs

        view = object.__new__(app.UMLCompilerApp)
        view.canvas_diagram = FakeCanvas()
        view.lbl_diagram_info = FakeWidget()

        view.render_class_diagram(self.result.model)

        texts = [kwargs["text"] for kind, _args, kwargs in view.canvas_diagram.items if kind == "text"]
        self.assertIn("[1:N]", texts)
        self.assertIn("placedOrder", texts)
        self.assertIn("1:N", view.lbl_diagram_info.config["text"])
        self.assertIn("placedOrder [1:N]", view.current_diagram_text)


if __name__ == "__main__":
    unittest.main()
