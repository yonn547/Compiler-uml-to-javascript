import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xtuml_compiler import (  # noqa: E402
    collect_state_machines,
    compile_text,
    to_mermaid_state,
    to_plantuml_state,
)
from xtuml_compiler.state_diagram import build_state_machine_layout  # noqa: E402


DSL_MODEL = ROOT / "examples" / "shop.xtuml"

CYCLE_MODEL = """
domain Demo {
  class Job {
    attribute id : string
    state machine cycle {
      event tick
      event finish
      state idle initial {
        entry: log("start")
      }
      state done final
      transition idle -> idle on tick
      transition idle -> done on finish
    }
  }
}
"""


class StateDiagramTests(unittest.TestCase):
    def setUp(self):
        self.result = compile_text(DSL_MODEL.read_text(encoding="utf-8"), format="dsl")
        self.assertTrue(self.result.ok, self.result.message)
        self.entries = collect_state_machines(self.result.model)
        self.assertEqual(len(self.entries), 1)
        self.class_name, self.machine = self.entries[0]

    def test_collect_and_result_properties(self):
        self.assertEqual(self.class_name, "Customer")
        self.assertEqual(self.machine.name, "lifecycle")
        self.assertEqual(self.result.state_diagram, to_plantuml_state(self.machine, self.class_name))
        self.assertIn("Customer.lifecycle", self.result.state_diagrams)

    def test_plantuml_state(self):
        puml = to_plantuml_state(self.machine, self.class_name)
        self.assertIn("@startuml", puml)
        self.assertIn("title Customer.lifecycle", puml)
        self.assertIn('state "new" as state_0', puml)
        self.assertIn("entry / log(", puml)
        self.assertIn("[*] --> state_0", puml)
        self.assertIn("state_0 --> state_1 : activate [self.name !=", puml)
        self.assertIn("state_1 --> state_2 : created", puml)
        self.assertIn("@enduml", puml)

    def test_mermaid_state(self):
        mermaid = to_mermaid_state(self.machine, self.class_name)
        self.assertTrue(mermaid.startswith("stateDiagram-v2"))
        self.assertIn('state "new" as state_0', mermaid)
        self.assertIn("note right of state_0 : entry / log('Customer dibuat')", mermaid)
        self.assertIn("[*] --> state_0", mermaid)
        self.assertIn("state_0 --> state_1 : activate [self.name !=", mermaid)

    def test_layout(self):
        layout = build_state_machine_layout(self.machine)
        self.assertFalse(layout.is_empty)
        self.assertEqual(len(layout.nodes), 4)  # 3 state + pseudo initial
        self.assertEqual(len(layout.edges), 3)
        self.assertEqual(len([edge for edge in layout.edges if edge.kind == "initial"]), 1)
        self.assertEqual(len([edge for edge in layout.edges if edge.kind == "transition"]), 2)
        self.assertGreater(layout.width, 0)
        self.assertGreater(layout.height, 0)

        initial = [node for node in layout.nodes if node.pseudo]
        self.assertEqual(len(initial), 1)
        self.assertTrue([node for node in layout.nodes if node.name == "new"][0].initial)

    def test_self_transition_and_final_state(self):
        result = compile_text(CYCLE_MODEL, format="dsl")
        self.assertTrue(result.ok, result.message)
        _, machine = collect_state_machines(result.model)[0]
        layout = build_state_machine_layout(machine)

        self_edges = [edge for edge in layout.edges if edge.is_self]
        self.assertEqual(len(self_edges), 1)
        self.assertEqual(self_edges[0].label, "tick")
        done = [node for node in layout.nodes if node.name == "done"]
        self.assertEqual(len(done), 1)
        self.assertTrue(done[0].final)

        puml = to_plantuml_state(machine, "Job")
        self.assertIn("state_0 --> state_0 : tick", puml)
        self.assertIn("state_1 --> [*]", puml)

    def test_cli_state_diagram_export(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "shop.puml"
            output = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "xtuml_compiler",
                    "compile",
                    str(DSL_MODEL),
                    "--state-diagram",
                    str(target),
                    "--quiet",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(output.returncode, 0, output.stderr)
            generated = Path(directory) / "shop.Customer.lifecycle.puml"
            self.assertTrue(generated.exists())
            self.assertIn("@startuml", generated.read_text(encoding="utf-8"))

            target_mmd = Path(directory) / "shop.mmd"
            output = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "xtuml_compiler",
                    "compile",
                    str(DSL_MODEL),
                    "--state-diagram",
                    str(target_mmd),
                    "--quiet",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(output.returncode, 0, output.stderr)
            generated_mmd = Path(directory) / "shop.Customer.lifecycle.mmd"
            self.assertTrue(
                generated_mmd.read_text(encoding="utf-8").startswith("stateDiagram-v2")
            )

    def test_gui_render_with_fake_canvas(self):
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

            def create_oval(self, *args, **kwargs):
                self.items.append(("oval", args, kwargs))
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

            def set(self, value):
                self.value = value

        view = object.__new__(app.UMLCompilerApp)
        view.canvas_state = FakeCanvas()
        view.lbl_state_info = FakeWidget()
        view.state_machine_option = FakeWidget()
        view.state_machine_entries = self.entries

        view.on_state_machine_selected("Customer.lifecycle")
        self.assertGreater(len(view.canvas_state.items), 0)
        self.assertIn("3 state", view.lbl_state_info.config["text"])
        self.assertTrue(view.current_state_diagram_text.startswith("@startuml"))

        view.populate_state_machines(self.result.model)
        self.assertEqual(view.state_machine_option.value, "Customer.lifecycle")


if __name__ == "__main__":
    unittest.main()
