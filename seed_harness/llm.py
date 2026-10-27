"""OpenAI-compatible JSON chat transport; no provider policy in the kernel."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from .registry import check
from .values import dumps


def settings(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not value.get("base_url") or not value.get("model"):
        raise ValueError("config requires base_url and model")
    return value


def complete(config, messages, schema):
    """Retry only invalid model text, never network operations or business tools."""
    messages = list(messages)
    for attempt in range(3):
        body = {"model": config["model"], "messages": messages}
        headers = {"Content-Type": "application/json"}
        if os.environ.get("OPENAI_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["OPENAI_API_KEY"]
        request = Request(config["base_url"].rstrip("/") + "/chat/completions",
                          dumps(body).encode("utf-8"), headers)
        try:
            with urlopen(request, timeout=config.get("timeout", 60)) as response:
                payload = json.load(response)
        except Exception:
            # Do not leak a server error body, credentials or request headers.
            raise RuntimeError("LLM transport failed; check endpoint and credentials") from None
        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty content")
            text = content.strip()
            if text.startswith("```") and text.endswith("```"):
                text = "\n".join(text.splitlines()[1:-1])
            value = json.loads(text)
            check(schema, value)
            return value
        except (ValueError, KeyError, IndexError, TypeError, __import__('jsonschema').ValidationError):
            if attempt == 2:
                raise ValueError("LLM returned invalid JSON/schema after 3 attempts") from None
            messages.append({"role": "user", "content": "Return only valid JSON matching this schema: " + dumps(schema)})
    raise AssertionError("unreachable")
