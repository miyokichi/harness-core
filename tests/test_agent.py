import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from seed_harness import Engine, Registry, Store
from seed_harness.agent import DECISION, build, decide
from seed_harness.llm import complete


def accept(state, result):
    return {"status": "pass" if result == 7 else "fail", "checks": ["expected seven"]}


class AgentTests(unittest.TestCase):
    def test_http_json_and_bounded_correction(self):
        replies = ["", "```json\n{\"ok\": true}\n```"]
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"choices": [{"message": {"content": replies.pop(0)}}]}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = {"base_url": 'http://127.0.0.1:' + str(server.server_port), "model": "fixture"}
        try:
            self.assertEqual(complete(config, [], {"type": "object"}), {"ok": True})
            self.assertEqual(len(received), 2)
            replies[:] = ["", '{"action":"unknown"}', '{"action":"finish","result":7,"evidence":""}']
            with self.assertRaises(ValueError):
                complete(config, [], DECISION)
            self.assertEqual(len(received), 5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_nonpublic_and_bad_arguments_rejected(self):
        tools = {"add": {"input_schema": {"type": "object", "required": ["x"]}}}
        for value in ({"action": "execute", "tool": "agent.learn", "arguments": {}},
                      {"action": "execute", "tool": "add", "arguments": {}}):
            with patch('seed_harness.agent.complete', return_value=value), self.assertRaises(Exception):
                decide({"request": {}}, {}, tools)

    def test_ask_restart_finish_and_failed_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            registry, flow = build({}, {}, 'tests.test_agent:accept')
            engine = Engine(registry, Store(Path(temp) / 'runs.db'))
            run = engine.start(flow, {"goal": "seven", "completion": "exactly seven"})
            with patch('seed_harness.agent.complete', return_value={"action": "ask", "question": "which?", "missing": "number"}):
                run = engine.drive(run['id'])
            self.assertEqual(run['status'], 'waiting')
            engine = Engine(Registry(), Store(Path(temp) / 'runs.db'))
            engine.resume(run['id'], {"number": 7}, pending_id=run['pending']['id'])
            with patch('seed_harness.agent.complete', return_value={"action": "finish", "result": 7, "evidence": "answer"}):
                run = engine.drive(run['id'])
            self.assertEqual(run['result']['verification']['status'], 'pass')
            run = Engine(registry, engine.store).start(flow, {})
            with patch('seed_harness.agent.complete', return_value={"action": "finish", "result": 8, "evidence": "guess"}):
                run = engine.drive(run['id'])
            self.assertEqual(run['status'], 'failed')
