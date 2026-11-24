import shutil
import unittest
from pathlib import Path

from xtuml_compiler import Simulator, compile_text


ROOT = Path(__file__).resolve().parents[1]
DSL_MODEL = ROOT / "examples" / "shop.xtuml"


@unittest.skipUnless(shutil.which("node"), "Node.js tidak tersedia")
class SimulatorTests(unittest.TestCase):
    def setUp(self):
        result = compile_text(DSL_MODEL.read_text(encoding="utf-8"), format="dsl")
        self.assertTrue(result.ok, result.message)
        self.simulator = Simulator()
        started, message = self.simulator.start(result.js)
        self.assertTrue(started, message)
        self.addCleanup(self.simulator.stop)

    def test_snapshot_and_events(self):
        snapshot = self.simulator.snapshot()
        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["domain"], "Shop")
        self.assertEqual([item["name"] for item in snapshot["instances"]], ["c1", "o1"])
        self.assertEqual(snapshot["instances"][0]["state"], "new")
        events = self.simulator.events("c1")
        self.assertIn("activate", events["events"])

    def test_send_and_reset(self):
        reply = self.simulator.send("c1", "activate")
        self.assertTrue(reply["ok"])
        self.assertTrue(reply["handled"])
        self.assertEqual(reply["state"], "active")
        self.assertEqual(reply["logs"], ["diaktifkan"])
        self.assertFalse(self.simulator.send("c1", "activate")["handled"])
        self.assertEqual(self.simulator.reset("c1")["state"], "new")

    def test_call_operation(self):
        reply = self.simulator.call("c1", "label")
        self.assertEqual(reply["result"], "Customer Alice")


if __name__ == "__main__":
    unittest.main()
