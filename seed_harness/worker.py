"""Standalone worker: only the standard library is needed in a target venv."""
import importlib
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    entry, request_path, result_path = sys.argv[1:]
    sys.path.insert(0, os.getcwd())
    try:
        module, name = entry.split(":", 1)
        function = importlib.import_module(module)
        for part in name.split("."):
            function = getattr(function, part)
        request = json.loads(Path(request_path).read_text(encoding="utf-8"))
        value = function(**request)
        payload = {"ok": True, "value": value}
        # Test serializability here, inside the exception boundary.
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except Exception as exc:
        traceback.print_exc()
        text = json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}},
                          ensure_ascii=False, allow_nan=False)
    target = Path(result_path)
    temp = target.with_suffix(".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, target)


if __name__ == "__main__":
    main()
