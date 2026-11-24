import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xtuml_compiler import compile_text  # noqa: E402
from xtuml_compiler.backend.js.expression import translate_expression  # noqa: E402


DSL_MODEL = ROOT / "examples" / "shop.xtuml"


class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.source = DSL_MODEL.read_text(encoding="utf-8")

    def test_dsl_pipeline(self):
        result = compile_text(self.source, format="dsl")
        self.assertTrue(result.ok, result.message)
        self.assertIn("class Customer", result.js)
        self.assertIn("new StateMachine", result.js)
        self.assertIn("new Association", result.js)
        self.assertIn("assoc_placedOrder.link(c1, o1);", result.js)

    def test_state_machine_transition_and_association(self):
        if not shutil.which("node"):
            self.skipTest("Node.js tidak tersedia")
        result = compile_text(self.source, format="dsl")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.js"
            path.write_text(result.js, encoding="utf-8")
            script = """
                const model = require(process.argv[1]);
                const customer = model.instances.c1;
                const order = model.instances.o1;
                if (customer.label() !== "Customer Alice") throw new Error("operation");
                if (customer.orders.length !== 1) throw new Error("association navigation");
                if (order.customer !== customer) throw new Error("reverse navigation");
                if (customer.state !== "new") throw new Error("initial state");
                if (!customer.generate("activate")) throw new Error("transition");
                if (customer.state !== "active") throw new Error("state after transition");
                if (customer.generate("activate")) throw new Error("guard should block");
                console.log("OK");
            """
            output = subprocess.run(
                ["node", "-e", script, str(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertTrue(output.stdout.strip().endswith("OK"), output.stdout)

    def test_project_mode(self):
        if not shutil.which("node"):
            self.skipTest("Node.js tidak tersedia")
        result = compile_text(self.source, format="dsl")
        self.assertIn("package.json", result.files)
        self.assertIn("src/classes/Customer.js", result.files)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in result.files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            index = root / "src" / "index.js"
            subprocess.run(["node", "--check", str(index)], check=True)
            script = f"""
                import("{index.as_uri()}").then((module) => {{
                    const customer = module.UmlModel.instances.c1;
                    if (customer.orders.length !== 1) throw new Error("project navigation");
                    console.log("OK");
                }}).catch((error) => {{ console.error(error); process.exit(1); }});
            """
            output = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(output.stdout.strip(), "OK")

    def test_ir_roundtrip(self):
        result = compile_text(self.source, format="dsl")
        self.assertTrue(result.ok, result.message)
        ir = json.loads(result.ir_json)
        self.assertEqual(ir["kind"], "xtuml-model")
        self.assertEqual(len(ir["classes"]), 2)
        second = compile_text(json.dumps(ir), format="json")
        self.assertTrue(second.ok, second.message)
        self.assertIn("class Customer", second.js)

    def test_legacy_formats(self):
        json_model = """
        {"objects": [{"name": "u1", "className": "User",
                      "attributes": {"name": "Alice"}}],
         "links": []}
        """
        plantuml = 'object user1 { name = "Alice" }\nuser1 -- user1 : selfLink\n'
        xml_model = """
        <uml>
          <object id="1" name="user1" class="User">
            <attribute name="name">Alice</attribute>
          </object>
        </uml>
        """
        for text, source_format in (
            (json_model, "json"),
            (plantuml, "plantuml"),
            (xml_model, "xml"),
        ):
            with self.subTest(format=source_format):
                result = compile_text(text, format=source_format)
                self.assertTrue(result.ok, result.message)
                self.assertIn("class User", result.js)

    def test_validator_errors(self):
        broken = """
        domain Broken {
          class A { attribute x : string }
          class A { attribute y : string }
          association rel between Ghost.ghosts [1] and A.items [1]
          link a1 to missing via rel
        }
        """
        result = compile_text(broken, format="dsl")
        self.assertFalse(result.ok)
        messages = result.message
        self.assertIn("duplikat", messages)
        self.assertIn("tidak ditemukan", messages)

    def test_multiplicity_violation(self):
        model = """
        domain Demo {
          class A { attribute id : string }
          class B { attribute id : string }
          association one between A.bs [1] and B.a [1]
          instance a1 of A { id = "a" }
          instance b1 of B { id = "b" }
          instance b2 of B { id = "c" }
          link a1 to b1 via one
          link a1 to b2 via one
        }
        """
        result = compile_text(model, format="dsl")
        self.assertFalse(result.ok)
        self.assertIn("maksimal 1", result.message)

    def test_expression_translation(self):
        self.assertEqual(
            translate_expression('self.name == "a\\"b" and not self.active'),
            'this.name == "a\\"b" && !this.active',
        )
        self.assertEqual(translate_expression("total mod 2 == 0"), "total % 2 == 0")

    def test_structured_xml(self):
        xml_source = """
        <xtuml name="Shop">
          <class name="Order">
            <attribute name="total" type="real"/>
            <state-machine name="lifecycle">
              <event name="confirm"/>
              <state name="pending" initial="true"/>
              <state name="paid" final="true"/>
              <transition from="pending" to="paid" event="confirm">
                log("lunas")
              </transition>
            </state-machine>
          </class>
          <instance name="o1" class="Order">
            <attribute name="total">150000</attribute>
          </instance>
        </xtuml>
        """
        result = compile_text(xml_source, format="xml")
        self.assertTrue(result.ok, result.message)
        self.assertIn("class Order", result.js)
        self.assertIn('"confirm"', result.js)

    def test_action_language_statements(self):
        if not shutil.which("node"):
            self.skipTest("Node.js tidak tersedia")
        model = """
        domain Demo {
          class Box {
            attribute value : integer
            operation run(limit : integer) : integer {
              let total = 0
              while (limit > 0) {
                total = total + limit
                limit = limit - 1
              }
              if (total >= 10) {
                log("besar")
              } else {
                log("kecil")
              }
              return total
            }
          }
          instance b1 of Box { value = 3 }
        }
        """
        result = compile_text(model, format="dsl")
        self.assertTrue(result.ok, result.message)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bundle.js"
            path.write_text(result.js, encoding="utf-8")
            script = """
                const model = require(process.argv[1]);
                if (model.instances.b1.run(5) !== 15) throw new Error("wrong result");
                console.log("OK");
            """
            output = subprocess.run(
                ["node", "-e", script, str(path)],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertTrue(output.stdout.strip().endswith("OK"), output.stdout)

    def test_cli(self):
        output = subprocess.run(
            [sys.executable, "-m", "xtuml_compiler", "check", str(DSL_MODEL)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(output.returncode, 0, output.stderr)


if __name__ == "__main__":
    unittest.main()
