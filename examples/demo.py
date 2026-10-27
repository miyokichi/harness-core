"""Two separate venvs + nested workflow + durable human answer + learned rule."""
import json
from pathlib import Path
import sys
import tempfile
import venv

from seed_harness import Engine, Registry, Store


def build_registry(root):
    specs = {}
    for name in ("initialize", "decide", "observe", "learn", "invalid"):
        specs[f"agent.{name}"] = {"kind": "python", "entry": f"examples.agent_tools:{name}"}
    specs["dimension.verify"] = {"kind": "python", "entry": "examples.agent_tools:verify_dimension"}
    for name in ("extract", "select"):
        directory = root / name
        venv.EnvBuilder(with_pip=False).create(directory / ".venv")
        python = directory / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        specs[f"dimension.{name}"] = {"kind": "subprocess", "entry": "tasks:run",
                                      "python": str(python.absolute()), "cwd": str(directory.absolute())}
    (root / "extract" / "tasks.py").write_text(
        'import sys\ndef run():\n print("日本語ファイル名：寸法表.pptx")\n return {"design": 42, "measured": 41.8, "unit": "nm", "environment": sys.prefix}\n', encoding="utf-8")
    (root / "select" / "tasks.py").write_text(
        'import sys\ndef run(document, selection):\n return {"value": document[selection], "unit": document["unit"], "selected": selection, "extract_environment": document["environment"], "select_environment": sys.prefix}\n', encoding="utf-8")
    specs["dimension.pipeline"] = {
        "kind": "workflow",
        "input_schema": {"type": "object", "properties": {"selection": {"enum": ["design", "measured"]}}, "required": ["selection"], "additionalProperties": False},
        "output_schema": {"type": "object", "required": ["value", "unit", "selected"]},
        "workflow": {"schema_version": 1, "id": "dimension-pipeline.v1", "entry": "extract", "nodes": {
            "extract": {"kind": "call", "tool": "dimension.extract", "input": {}, "next": "select"},
            "select": {"kind": "call", "tool": "dimension.select", "input": {
                "document": {"$ref": "steps.extract"}, "selection": {"$ref": "input.selection"}}, "next": "verify"},
            "verify": {"kind": "call", "tool": "dimension.verify", "input": {
                "result": {"$ref": "steps.select"}, "selection": {"$ref": "input.selection"}}, "next": "finish"},
            "finish": {"kind": "return", "value": {"$ref": "steps.verify"}}}}
    }
    return Registry(specs)


def main():
    with tempfile.TemporaryDirectory(prefix="seed-demo-") as tmp:
        root = Path(tmp)
        registry = build_registry(root)
        flow = json.loads(Path(__file__).with_name("agent_loop.json").read_text(encoding="utf-8"))
        store = Store(root / "state.sqlite3")
        engine = Engine(registry, store)
        arguments = {"knowledge_db": str(root / "knowledge.sqlite3")}
        first = engine.drive(engine.start(flow, arguments)["id"])
        assert first["status"] == "waiting", first
        print("1. 不明条件を検出し、質問して停止:", first["pending"]["question"])
        engine = Engine(Registry(), Store(root / "state.sqlite3"))
        engine.resume(first["id"], {"selection": "design"}, pending_id=first["pending"]["id"])
        first = engine.drive(first["id"])
        assert first["status"] == "completed", first
        assert first["result"]["value"] == 42
        assert first["result"]["verification"]["status"] == "pass"
        assert first["result"]["extract_environment"] != first["result"]["select_environment"]
        print("2. 再起動後、回答を保存して再開:", first["result"]["value"], first["result"]["unit"])
        second_engine = Engine(registry, store)
        second = second_engine.drive(second_engine.start(flow, arguments)["id"])
        assert second["status"] == "completed", second
        assert not any(e["event"]["type"] == "waiting" for e in store.events(second["id"]))
        logs = list((root / "artifacts").rglob("stdout.log"))
        assert any("寸法表.pptx" in p.read_text(encoding="utf-8") for p in logs)
        print("3. 同じ条件の次回実行は質問なしで完了")
        print("PASS: 異なるvenv・日本語ログ・入れ子・停止再開・知識再利用")


if __name__ == "__main__":
    main()
