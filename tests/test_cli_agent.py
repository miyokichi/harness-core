import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from seed_harness import Store


class AgentCLITests(unittest.TestCase):
    def test_job_exits_answer_in_new_process_and_no_repeated_tool(self):
        decisions = [
            {'action': 'execute', 'tool': 'seven', 'arguments': {}},
            {'action': 'ask', 'question': '承認しますか？', 'missing': 'approval'},
            {'action': 'finish', 'result': 7, 'evidence': 'seven and approval'}]
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'choices': [{'message': {'content': json.dumps(decisions.pop(0))}}]}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                config = root / 'config.json'
                config.write_text(json.dumps({'base_url': 'http://127.0.0.1:' + str(server.server_port), 'model': 'fixture'}), encoding='utf-8')
                registry = root / 'registry.json'
                registry.write_text(json.dumps({'seven': {'kind': 'python', 'entry': 'tests.test_extensions:seven'}}), encoding='utf-8')
                db = root / 'runs.db'
                command = [sys.executable, '-m', 'seed_harness.cli', '--db', str(db)]
                env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
                def call(arguments):
                    return json.loads(subprocess.run(command + arguments, capture_output=True, text=True, encoding='utf-8', check=True, env=env).stdout)
                run = call(['job', 'seven then approval', '--completion', 'result equals seven', '--config', str(config),
                            '--registry', str(registry), '--verifier', 'tests.test_agent:accept', '--json'])
                self.assertEqual(run['status'], 'waiting')
                answer = root / 'answer.json'
                answer.write_text('{"approved":true}', encoding='utf-8')
                run = call(['resume', run['id'], '--pending-id', run['pending']['id'], '--answer', str(answer), '--drive'])
                self.assertEqual(run['status'], 'completed')
                events = Store(db).events(run['id'])
                self.assertEqual(len([e for e in events if e['event'].get('tool') == 'seven']), 1)
                state = json.loads(requests[-1]['messages'][1]['content'])['state']
                self.assertEqual(state['history'][0]['decision']['tool'], 'seven')
                self.assertEqual(state['history'][1]['decision']['question'], '承認しますか？')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
