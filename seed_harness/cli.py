import argparse
import json
from pathlib import Path

from .engine import Engine
from .registry import Registry
from .store import Store
from .values import dumps


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def present(value):
    print(f"run_id={value['id']} status={value['status']}")
    if value.get("pending"):
        print(f"質問: {value['pending']['question']}\npending_id={value['pending']['id']}")
    if value.get("error"):
        print("失敗: " + value['error']['message'])
    if value['status'] == 'completed':
        print(dumps(value['result']))


def interact(engine, value):
    while value['status'] in {'ready', 'waiting'}:
        if value['status'] == 'ready':
            value = engine.drive(value['id'])
            continue
        present(value)
        try:
            answer = json.loads(input('回答 (JSON object; Ctrl+Cで終了): '))
            value = engine.resume(value['id'], answer, pending_id=value['pending']['id'])
        except (EOFError, KeyboardInterrupt):
            print('\n保存済み。run_idから再開できます。')
            break
        except (ValueError, __import__('jsonschema').ValidationError) as exc:
            print('回答が不正: ' + str(exc))
    return value


def main():
    parser = argparse.ArgumentParser(description="Durable function/workflow kernel")
    parser.add_argument("--db", default="runs/state.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    job = commands.add_parser("job", help="Start a natural-language job")
    job.add_argument("goal")
    job.add_argument("--config", default="harness.json")
    job.add_argument("--registry", required=True, help="Public business tools only")
    job.add_argument("--completion", required=True)
    job.add_argument("--verifier", required=True, help="Trusted module:function(state, result)")
    job.add_argument("--interactive", action="store_true")
    job.add_argument("--json", action="store_true")
    job.add_argument("--checked", action="store_true")
    talk = commands.add_parser("talk", help="Continue saved run interactively")
    talk.add_argument("run_id")
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
            cmd.add_argument("--drive", action="store_true")
        if command == "recover":
            cmd.add_argument("--expected-token", required=True)
    args = parser.parse_args()
    store = Store(args.db)
    engine = Engine(Registry(), store)
    if args.command == "job":
        from .agent import build
        from .llm import settings
        engine.registry, flow = build(settings(args.config), read(args.registry), args.verifier, args.checked)
        value = engine.start(flow, {"goal": args.goal, "completion": args.completion})
        value = engine.drive(value['id'])
        if args.interactive:
            value = interact(engine, value)
    elif args.command == "talk":
        value = interact(engine, store.load(args.run_id))
    elif args.command == "start":
        engine.registry = Registry(read(args.registry))
        value = engine.start(read(args.workflow), read(args.input), max_steps=args.max_steps)
    elif args.command == "run":
        value = engine.drive(args.run_id, max_ticks=args.max_ticks)
    elif args.command == "resume":
        value = engine.resume(args.run_id, read(args.answer), pending_id=args.pending_id)
        if args.drive:
            value = engine.drive(args.run_id)
    elif args.command == "recover":
        value = engine.recover(args.run_id, expected_token=args.expected_token)
    elif args.command == "retry":
        value = engine.retry(args.run_id)
    elif args.command == "events":
        value = store.events(args.run_id)
    else:
        value = store.load(args.run_id)
    if args.command == 'talk' or args.command == 'job' and not args.json:
        present(value)
    else:
        print(dumps(value))


if __name__ == "__main__":
    main()
