import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xtuml_compiler import (  # noqa: E402
    build_class_diagram_layout,
    compile_text,
    to_mermaid,
    to_plantuml,
)


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
        self.assertIn('Customer "1" -- "0..*" Order : placedOrder', puml)
        self.assertIn("@enduml", puml)

    def test_mermaid_from_compile_result(self):
        mermaid = to_mermaid(self.result.model)
        self.assertEqual(self.result.mermaid_diagram, mermaid)
        self.assertTrue(mermaid.startswith("classDiagram"))
        self.assertIn("+string name", mermaid)
        self.assertIn("+label() string", mermaid)
        self.assertIn('Customer "1" -- "0..*" Order : placedOrder', mermaid)

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


if __name__ == "__main__":
    unittest.main()
