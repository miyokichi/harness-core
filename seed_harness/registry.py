"""Explicit trusted registrations. Manifests contain no live Python objects."""
import importlib
import math
from pathlib import Path

from jsonschema import Draft202012Validator

from .values import clone


def check(schema, value):
    Draft202012Validator(schema).validate(value)


def validate_flow(flow):
    if flow.get("schema_version") != 1:
        raise ValueError("workflow schema_version must be 1")
    for field in ("input_schema", "output_schema"):
        Draft202012Validator.check_schema(flow.get(field, {}))
    nodes = flow.get("nodes")
    if not isinstance(nodes, dict) or not nodes or flow.get("entry") not in nodes:
        raise ValueError("workflow needs nodes and a valid entry")
    for name, node in nodes.items():
        if not isinstance(name, str) or not name or "." in name:
            raise ValueError("node IDs must be non-empty strings without dots")
        kind = node.get("kind")
        if "save_as" in node and (not isinstance(node["save_as"], str) or not node["save_as"] or "." in node["save_as"]):
            raise ValueError("save_as must be a non-empty variable name without dots")
        if kind not in {"call", "branch", "wait", "return"}:
            raise ValueError(f"unknown node kind: {kind}")
        targets = []
        if kind in {"call", "wait"}:
            targets.append(node.get("next"))
        tool = node.get("tool")
        if kind == "call" and not (isinstance(tool, str) or
                isinstance(tool, dict) and set(tool) == {"$ref"} and isinstance(tool["$ref"], str)):
            raise ValueError(f"{name}: call needs tool ID or explicit $ref")
        if kind == "wait":
            if "question" not in node:
                raise ValueError(f"{name}: wait needs question")
            Draft202012Validator.check_schema(node.get("answer_schema", {}))
        if kind == "branch":
            if "value" not in node or not isinstance(node.get("cases"), dict) or "default" not in node:
                raise ValueError(f"{name}: branch needs value, cases and default")
            targets.extend(node["cases"].values())
            targets.append(node["default"])
        if "on_error" in node:
            targets.append(node["on_error"])
        if any(t not in nodes for t in targets):
            raise ValueError(f"{name}: transition points to a missing node")


def load_entry(entry):
    module, sep, name = entry.partition(":")
    if not sep or not module or not name:
        raise ValueError("entry must be module:function")
    obj = importlib.import_module(module)
    for part in name.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise TypeError(f"not callable: {entry}")
    return obj


class Registry:
    def __init__(self, specs=None):
        self.specs = {}
        for name, spec in (specs or {}).items():
            self.register(name, spec)

    def register(self, name, spec):
        if name in self.specs:
            raise ValueError(f"already registered: {name}; use a new ID/version")
        spec = clone(spec)
        if spec.get("kind") not in {"python", "subprocess", "workflow"}:
            raise ValueError("tool kind must be python, subprocess, or workflow")
        for field in ("input_schema", "output_schema"):
            Draft202012Validator.check_schema(spec.get(field, {}))
        if spec["kind"] == "workflow":
            validate_flow(spec["workflow"])
        else:
            if not isinstance(spec.get("entry"), str) or ":" not in spec["entry"]:
                raise ValueError("tool needs module:function entry")
        if spec["kind"] == "subprocess":
            for field in ("python", "cwd"):
                if not Path(spec[field]).is_absolute():
                    raise ValueError(f"subprocess {field} must be absolute")
            timeout = spec.get("timeout", 300)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("timeout must be a positive finite number")
        self.specs[name] = spec

    def snapshot(self):
        return clone(self.specs)
