"""Strict JSON values and explicit references, without eval or interpolation."""
import copy
import json


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def clone(value):
    return json.loads(dumps(value))


def resolve(value, scope):
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            path = value["$ref"]
            if not isinstance(path, str) or not path:
                raise ValueError("$ref must be a non-empty dotted path")
            current = scope
            for key in path.split("."):
                if isinstance(current, list):
                    current = current[int(key)]
                else:
                    current = current[key]
            return copy.deepcopy(current)
        if "$ref" in value:
            raise ValueError("$ref cannot be combined with other keys")
        return {k: resolve(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, scope) for v in value]
    return value
