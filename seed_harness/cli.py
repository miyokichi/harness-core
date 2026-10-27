import argparse
import json
from pathlib import Path

from .engine import Engine
from .registry import Registry
from .store import Store
from .values import dumps


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Durable function/workflow kernel")
    parser.add_argument("--db", default="runs/state.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("workflow")
    start.add_argument("--registry", required=True)
    start.add_argument("--input", required=True, help="UTF-8 JSON file")
    start.add_argument("--max-steps", type=int, default=1000)
    for command in ("run", "status", "events", "retry", "recover", "resume"):
        cmd = commands.add_parser(command)
        cmd.add_argument("run_id")
        if command == "run":
            cmd.add_argument("--max-ticks", type=int, default=100)
        if command == "resume":
            cmd.add_argument("--answer", required=True, help="UTF-8 JSON file")
            cmd.add_argument("--pending-id", required=True)
        if command == "recover":
            cmd.add_argument("--expected-token", required=True)
    args = parser.parse_args()
    store = Store(args.db)
    engine = Engine(Registry(), store)
    if args.command == "start":
        engine.registry = Registry(read(args.registry))
        value = engine.start(read(args.workflow), read(args.input), max_steps=args.max_steps)
    elif args.command == "run":
        value = engine.drive(args.run_id, max_ticks=args.max_ticks)
    elif args.command == "resume":
        value = engine.resume(args.run_id, read(args.answer), pending_id=args.pending_id)
    elif args.command == "recover":
        value = engine.recover(args.run_id, expected_token=args.expected_token)
    elif args.command == "retry":
        value = engine.retry(args.run_id)
    elif args.command == "events":
        value = store.events(args.run_id)
    else:
        value = store.load(args.run_id)
    print(dumps(value))


if __name__ == "__main__":
    main()
