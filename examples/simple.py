"""No LLM, API key or separate venv required. Run from the project root."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from seed_harness import Engine, Registry, Store


def greet(name):
    return {"message": f"こんにちは、{name}さん"}


def definition():
    return {
        "schema_version": 1, "id": "greeting.v1", "entry": "ask",
        "nodes": {
            "ask": {"kind": "wait", "question": "名前を教えてください",
                    "answer_schema": {"type": "string", "minLength": 1}, "next": "greet"},
            "greet": {"kind": "call", "tool": "greet",
                      "input": {"name": {"$ref": "steps.ask"}}, "next": "finish"},
            "finish": {"kind": "return", "value": {"$ref": "steps.greet"}},
        },
    }


def main():
    registry = Registry({"greet": {"kind": "python", "entry": "examples.simple:greet"}})
    with TemporaryDirectory() as directory:
        database = Path(directory) / "state.sqlite3"
        engine = Engine(registry, Store(database))
        run = engine.start(definition(), {})
        run = engine.drive(run["id"])
        print("停止:", run["pending"]["question"])
        # The UI/LLM can be replaced without changing the engine.
        # This non-interactive demo supplies a fixed answer.
        restarted = Engine(Registry(), Store(database))
        restarted.resume(run["id"], "太郎", pending_id=run["pending"]["id"])
        run = restarted.drive(run["id"])
        if run["status"] != "completed":
            raise RuntimeError(run)
        print("再開:", json.dumps(run["result"], ensure_ascii=False))


if __name__ == "__main__":
    main()
