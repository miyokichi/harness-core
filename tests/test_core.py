import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from jsonschema import ValidationError

from seed_harness import Conflict, Engine, Registry, Store
from seed_harness import knowledge
from seed_harness.registry import validate_flow
from seed_harness.values import resolve
from tests import fixtures


def flow(nodes, entry=None, **kwargs):
    return dict(schema_version=1, entry=entry or next(iter(nodes)), nodes=nodes, **kwargs)


def python_tool(name, **kwargs):
    return dict(kind="python", entry=f"tests.fixtures:{name}", **kwargs)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "state.db")
        self.registry = Registry({"identity": python_tool("identity"), "add": python_tool("add"), "fail": python_tool("fail")})
        self.engine = Engine(self.registry, self.store)

    def run_flow(self, f, arguments=None, **kwargs):
        state = self.engine.start(f, arguments or {}, **kwargs)
        return self.engine.drive(state["id"])

    def test_reference_and_literal_strings(self):
        scope = {"input": {"x": [4, 9]}}
        self.assertEqual(resolve({"$ref": "input.x.1"}, scope), 9)
        self.assertEqual(resolve("${input.x}", scope), "${input.x}")
        with self.assertRaises(KeyError):
            resolve({"$ref": "input.missing"}, scope)

    def test_branch_loop_and_variables(self):
        f = flow({
            "init": {"kind": "call", "tool": "identity", "input": {"value": 0}, "save_as": "counter", "next": "inc"},
            "inc": {"kind": "call", "tool": "add", "input": {"value": {"$ref": "vars.counter"}}, "save_as": "counter", "next": "branch"},
            "branch": {"kind": "branch", "value": {"$ref": "vars.counter"}, "cases": {"3": "end"}, "default": "inc"},
            "end": {"kind": "return", "value": {"$ref": "vars.counter"}}})
        state = self.run_flow(f)
        self.assertEqual((state["status"], state["result"]), ("completed", 3))

    def test_wait_resume_in_new_engine_and_stale_answer(self):
        f = flow({"ask": {"kind": "wait", "question": "寸法は？", "answer_schema": {"type": "integer"}, "next": "end"},
                  "end": {"kind": "return", "value": {"$ref": "steps.ask"}}})
        state = self.run_flow(f)
        run_id, pending = state["id"], state["pending"]["id"]
        new = Engine(Registry(), Store(self.root / "state.db"))
        with self.assertRaises(ValidationError):
            new.resume(run_id, "wrong", pending_id=pending)
        with self.assertRaises(Conflict):
            new.resume(run_id, 42, pending_id="stale")
        new.resume(run_id, 42, pending_id=pending)
        with self.assertRaises(Conflict):
            new.resume(run_id, 43, pending_id=pending)
        self.assertEqual(new.drive(run_id)["result"], 42)

    def test_nested_wait_and_same_tool_interface(self):
        child = flow({"ask": {"kind": "wait", "question": "value?", "next": "end"},
                      "end": {"kind": "return", "value": {"$ref": "steps.ask"}}})
        self.registry.register("child", {"kind": "workflow", "workflow": child, "output_schema": {"type": "number"}})
        parent = flow({"call": {"kind": "call", "tool": "child", "save_as": "answer", "next": "end"},
                       "end": {"kind": "return", "value": {"$ref": "vars.answer"}}})
        state = self.run_flow(parent)
        self.assertEqual(len(state["stack"]), 2)
        self.engine.resume(state["id"], 8, pending_id=state["pending"]["id"])
        self.assertEqual(self.engine.drive(state["id"])["result"], 8)

    def test_runtime_dispatch_rejects_unknown_tool(self):
        f = flow({"call": {"kind": "call", "tool": {"$ref": "input.tool"}, "next": "end"},
                  "end": {"kind": "return"}})
        state = self.run_flow(f, {"tool": "not-registered"})
        self.assertEqual(state["status"], "failed")
        self.assertIn("unregistered", state["error"]["message"])

    def test_input_output_schema_and_root_contract(self):
        self.registry.register("number", python_tool("identity", input_schema={"type": "object", "properties": {"value": {"type": "number"}}, "required": ["value"]}, output_schema={"type": "integer"}))
        f = flow({"call": {"kind": "call", "tool": "number", "input": {"value": {"$ref": "input.value"}}, "next": "end"},
                  "end": {"kind": "return", "value": {"$ref": "steps.call"}}})
        self.assertEqual(self.run_flow(f, {"value": "bad"})["error"]["type"], "ValidationError")
        self.assertEqual(self.run_flow(f, {"value": 1.5})["error"]["type"], "ValidationError")
        self.assertEqual(self.run_flow(f, {"value": 2})["result"], 2)
        f["input_schema"] = {"type": "object", "required": ["value"]}
        with self.assertRaises(ValidationError):
            self.engine.start(f, {})

    def test_schema_and_transition_definition_validation(self):
        with self.assertRaises(ValueError):
            validate_flow(flow({"x": {"kind": "call", "tool": "identity", "next": "missing"}}))
        with self.assertRaises(ValueError):
            Registry({"bad": dict(kind="subprocess", python="relative/python", cwd="relative", entry="x:y")})

    def test_failure_caught_by_parent_workflow(self):
        child = flow({"boom": {"kind": "call", "tool": "fail", "next": "end"}, "end": {"kind": "return"}})
        self.registry.register("child", {"kind": "workflow", "workflow": child})
        f = flow({"call": {"kind": "call", "tool": "child", "on_error": "caught", "next": "end"},
                  "caught": {"kind": "return", "value": {"$ref": "steps.call.error.type"}},
                  "end": {"kind": "return", "value": "unexpected"}})
        self.assertEqual(self.run_flow(f)["result"], "RuntimeError")

    def test_nonfinite_output_rejected(self):
        self.registry.register("nan", python_tool("invalid_number"))
        f = flow({"x": {"kind": "call", "tool": "nan", "next": "end"}, "end": {"kind": "return"}})
        self.assertEqual(self.run_flow(f)["status"], "failed")

    def test_context_has_stable_run_identity(self):
        self.registry.register("context", python_tool("context", context=True))
        f = flow({"x": {"kind": "call", "tool": "context", "next": "end"}, "end": {"kind": "return", "value": {"$ref": "steps.x"}}})
        state = self.run_flow(f)
        self.assertEqual(state["result"]["run_id"], state["id"])

    def test_snapshot_pins_flow_and_tool_definition(self):
        f = flow({"x": {"kind": "call", "tool": "add", "input": {"value": 3}, "next": "end"},
                  "end": {"kind": "return", "value": {"$ref": "steps.x"}}})
        state = self.engine.start(f, {})
        f["nodes"]["x"]["input"]["value"] = 100
        self.registry.specs["add"]["entry"] = "tests.fixtures:fail"
        new = Engine(Registry(), self.store)
        self.assertEqual(new.drive(state["id"])["result"], 4)

    def test_loop_budget(self):
        f = flow({"loop": {"kind": "branch", "value": "x", "cases": {}, "default": "loop"}})
        state = self.run_flow(f, max_steps=4)
        self.assertEqual((state["status"], state["error"]["type"], state["steps"]), ("failed", "StepLimit", 4))
        with self.assertRaises(Conflict):
            self.engine.retry(state["id"])

    def test_revision_conflict(self):
        state = self.engine.start(flow({"end": {"kind": "return"}}), {})
        stale = self.store.load(state["id"])
        self.store.save(state, {"type": "first"})
        with self.assertRaises(Conflict):
            self.store.save(stale, {"type": "stale"})

    def test_concurrent_tick_does_not_execute_twice(self):
        fixtures.entered.clear()
        fixtures.release.clear()
        fixtures.calls = 0
        self.registry.register("blocked", python_tool("blocked"))
        f = flow({"x": {"kind": "call", "tool": "blocked", "next": "end"}, "end": {"kind": "return"}})
        state = self.engine.start(f, {})
        errors = []
        def tick():
            try:
                self.engine.tick(state["id"])
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=tick)
        worker.start()
        try:
            self.assertTrue(fixtures.entered.wait(3))
            with self.assertRaises(Conflict):
                self.engine.tick(state["id"])
        finally:
            fixtures.release.set()
            worker.join(5)
        self.assertFalse(errors)
        self.assertEqual(fixtures.calls, 1)

    def test_explicit_recovery_does_not_replay(self):
        state = self.engine.start(flow({"end": {"kind": "return", "value": 7}}), {})
        state.update(status="running", active={"token": "crashed"})
        self.store.save(state, {"type": "simulate_crash"})
        with self.assertRaises(Conflict):
            self.engine.tick(state["id"])
        with self.assertRaises(Conflict):
            self.engine.recover(state["id"], expected_token="wrong")
        recovered = self.engine.recover(state["id"], expected_token="crashed")
        self.assertEqual(recovered["status"], "failed")
        self.assertEqual(self.engine.drive(state["id"])["status"], "failed")
        self.engine.retry(state["id"])
        self.assertEqual(self.engine.drive(state["id"])["result"], 7)

    def test_subprocess_utf8_noise_and_result_separation(self):
        directory = self.root / "日本語プロジェクト"
        directory.mkdir()
        (directory / "tasks.py").write_text('import sys\ndef run(name):\n print("ログ："+name)\n print("注意", file=sys.stderr)\n return {"name": name}\n', encoding="utf-8")
        self.registry.register("worker", dict(kind="subprocess", python=sys.executable, cwd=str(directory), entry="tasks:run"))
        f = flow({"x": {"kind": "call", "tool": "worker", "input": {"name": "寸法.xlsx"}, "next": "end"},
                  "end": {"kind": "return", "value": {"$ref": "steps.x"}}})
        state = self.run_flow(f)
        self.assertEqual(state["result"], {"name": "寸法.xlsx"})
        out = next((self.root / "artifacts").rglob("stdout.log"))
        self.assertIn("ログ：寸法.xlsx", out.read_text(encoding="utf-8"))

    def test_subprocess_timeout_failure_and_serialization(self):
        directory = self.root / "worker"
        directory.mkdir()
        (directory / "tasks.py").write_text('import time\ndef sleep():\n time.sleep(3)\ndef bad():\n raise ValueError("日本語エラー")\ndef nan():\n return float("nan")\n', encoding="utf-8")
        for name, timeout, expected in (("sleep", 0.1, "TimeoutExpired"), ("bad", 5, "RuntimeError"), ("nan", 5, "RuntimeError")):
            self.registry.register(name, dict(kind="subprocess", python=sys.executable, cwd=str(directory), entry=f"tasks:{name}", timeout=timeout))
            f = flow({"x": {"kind": "call", "tool": name, "next": "end"}, "end": {"kind": "return"}})
            state = self.run_flow(f)
            self.assertEqual(state["error"]["type"], expected)

    def test_knowledge_scope_idempotency_and_conflict(self):
        db = str(self.root / "knowledge.db")
        knowledge.remember(db, "GDR", "dimension", "design", "user", ["measurement requested"])
        knowledge.remember(db, "GDR", "dimension", "design", "user", ["measurement requested"])
        self.assertFalse(knowledge.lookup(db, "other", "dimension")["found"])
        self.assertEqual(knowledge.lookup(db, "GDR", "dimension")["record"]["value"], "design")
        with self.assertRaises(ValueError):
            knowledge.remember(db, "GDR", "dimension", "measured", "user")

    def test_cli_resume_in_separate_process(self):
        (self.root / "flow.json").write_text(json.dumps(flow({"ask": {"kind": "wait", "question": "value?", "next": "end"}, "end": {"kind": "return", "value": {"$ref": "steps.ask"}}})), encoding="utf-8")
        (self.root / "registry.json").write_text("{}", encoding="utf-8")
        (self.root / "input.json").write_text("{}", encoding="utf-8")
        (self.root / "answer.json").write_text('"回答"', encoding="utf-8")
        def cli(*args):
            command = [sys.executable, "-m", "seed_harness.cli", "--db", self.store.path, *args]
            result = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8",
                                    env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
            return json.loads(result.stdout)
        state = cli("start", str(self.root / "flow.json"), "--registry", str(self.root / "registry.json"), "--input", str(self.root / "input.json"))
        state = cli("run", state["id"])
        cli("resume", state["id"], "--pending-id", state["pending"]["id"], "--answer", str(self.root / "answer.json"))
        self.assertEqual(cli("run", state["id"])["result"], "回答")

    def test_wait_resume_does_not_repeat_successful_side_effect(self):
        marker = self.root / "marker.txt"
        self.registry.register("write", python_tool("append_marker"))
        f = flow({"write": {"kind": "call", "tool": "write", "input": {"path": str(marker)}, "next": "ask"},
                  "ask": {"kind": "wait", "question": "continue?", "next": "end"},
                  "end": {"kind": "return", "value": {"$ref": "steps.write"}}})
        state = self.run_flow(f)
        restarted = Engine(Registry(), Store(self.root / "state.db"))
        restarted.resume(state["id"], True, pending_id=state["pending"]["id"])
        self.assertEqual(restarted.drive(state["id"])["result"], {"written": True})
        self.assertEqual(marker.read_text(encoding="utf-8"), "実行済み\n")

    def test_real_host_process_crash_preserves_unknown_outcome(self):
        marker = self.root / "crash-marker.txt"
        self.registry.register("crash", python_tool("crash_after_write"))
        f = flow({"crash": {"kind": "call", "tool": "crash", "input": {"path": str(marker)}, "next": "end"},
                  "end": {"kind": "return"}})
        state = self.engine.start(f, {})
        result = subprocess.run([sys.executable, "-m", "seed_harness.cli", "--db", self.store.path, "run", state["id"]], capture_output=True)
        self.assertEqual(result.returncode, 73)
        interrupted = self.store.load(state["id"])
        self.assertEqual(interrupted["status"], "running")
        self.engine.recover(state["id"], expected_token=interrupted["active"]["token"])
        self.assertEqual(self.engine.drive(state["id"])["status"], "failed")
        self.assertEqual(marker.read_text(encoding="utf-8"), "実行済み\n")

    def test_failed_child_return_keeps_frame_for_inspection(self):
        child = flow({"end": {"kind": "return", "value": "bad"}})
        self.registry.register("child", {"kind": "workflow", "workflow": child, "output_schema": {"type": "number"}})
        parent = flow({"child": {"kind": "call", "tool": "child", "next": "end"}, "end": {"kind": "return"}})
        state = self.run_flow(parent)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(len(state["stack"]), 2)
        self.assertEqual(state["stack"][-1]["pc"], "end")


if __name__ == "__main__":
    unittest.main()
