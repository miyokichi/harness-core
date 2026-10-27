"""Execution transport. JSON results are separate from stdout/stderr logs."""
import json
import os
from pathlib import Path
import subprocess

from .registry import check, load_entry
from .values import clone, dumps


def invoke(spec, arguments, context, directory):
    check(spec.get("input_schema", {}), arguments)
    if not isinstance(arguments, dict):
        raise TypeError("tool input must be an object for keyword arguments")
    if spec["kind"] == "python":
        kwargs = dict(arguments)
        if spec.get("context", False):
            if "_context" in kwargs:
                raise ValueError("_context is reserved")
            kwargs["_context"] = context
        result = load_entry(spec["entry"])(**kwargs)
    elif spec["kind"] == "subprocess":
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        request = directory / "request.json"
        response = directory / "response.json"
        request.write_text(dumps(arguments), encoding="utf-8")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
            subprocess.run([spec["python"], str(Path(__file__).with_name("worker.py")),
                            spec["entry"], str(request), str(response)],
                           cwd=spec["cwd"], env=env, stdin=subprocess.DEVNULL,
                           stdout=out, stderr=err, check=True, timeout=spec.get("timeout", 300))
        payload = json.loads(response.read_text(encoding="utf-8"))
        if not payload["ok"]:
            raise RuntimeError(f"worker {payload['error']['type']}: {payload['error']['message']}")
        result = payload["value"]
    else:
        raise ValueError("workflow tools must be executed by the engine")
    result = clone(result)
    check(spec.get("output_schema", {}), result)
    return result
