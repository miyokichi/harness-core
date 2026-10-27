"""Small durable interpreter. Agent policy, learning and repair live above it."""
from pathlib import Path
import uuid

from .executor import invoke
from .registry import check, validate_flow
from .store import Conflict
from .values import clone, dumps, resolve


def frame(flow, arguments, parent=None, output_schema=None):
    return {"flow": clone(flow), "pc": flow["entry"],
            "scope": {"input": clone(arguments), "steps": {}, "vars": {}},
            "parent": parent, "output_schema": output_schema or {}}


def store_output(current, node_id, value):
    current["scope"]["steps"][node_id] = value
    node = current["flow"]["nodes"][node_id]
    if "save_as" in node:
        current["scope"]["vars"][node["save_as"]] = clone(value)


class Engine:
    def __init__(self, registry, store, artifacts=None):
        self.registry = registry
        self.store = store
        self.artifacts = str(Path(artifacts or Path(store.path).parent / "artifacts").absolute())

    def start(self, flow, arguments, *, max_steps=1000):
        validate_flow(flow)
        if type(max_steps) is not int or max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")
        check(flow.get("input_schema", {}), arguments)
        specs = self.registry.snapshot()
        for candidate in [flow] + [s["workflow"] for s in specs.values() if s["kind"] == "workflow"]:
            for node in candidate["nodes"].values():
                if node["kind"] == "call" and isinstance(node["tool"], str) and node["tool"] not in specs:
                    raise ValueError(f"unregistered tool: {node['tool']}")
        return self.store.create({"format_version": 1, "status": "ready", "stack": [frame(flow, arguments)],
                                  "tools": specs, "steps": 0, "max_steps": max_steps,
                                  "artifacts": self.artifacts, "result": None, "error": None,
                                  "pending": None, "active": None})

    def tick(self, run_id):
        state = self.store.load(run_id)
        if state["status"] == "running":
            raise Conflict("run is executing or interrupted; inspect it before recover()")
        if state["status"] != "ready":
            return state
        if state["steps"] >= state["max_steps"]:
            state.update(status="failed", error={"type": "StepLimit", "message": "maximum total steps reached"})
            return self.store.save(state, {"type": "step_limit"})
        current = state["stack"][-1]
        node_id = current["pc"]
        node = current["flow"]["nodes"][node_id]
        token = uuid.uuid4().hex
        state.update(status="running", active={"token": token, "node": node_id,
                                               "depth": len(state["stack"]), "step": state["steps"]})
        self.store.save(state, {"type": "started", **state["active"]})
        state["steps"] += 1
        # Work on a copy; an exception must not leave a half-popped stack.
        working = clone(state)
        try:
            event = self._step(working, node, token)
            state = working
            if state["status"] == "running":
                state["status"] = "ready"
            state["error"] = None
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc), "node": node_id,
                     "depth": len(state["stack"])}
            handled = False
            for index in range(len(state["stack"]) - 1, -1, -1):
                candidate = state["stack"][index]
                candidate_id = candidate["pc"]
                candidate_node = candidate["flow"]["nodes"][candidate_id]
                if "on_error" in candidate_node:
                    del state["stack"][index + 1:]
                    store_output(candidate, candidate_id, {"error": error})
                    candidate["pc"] = candidate_node["on_error"]
                    state.update(status="ready", error=None)
                    handled = True
                    break
            if not handled:
                state.update(status="failed", error=error)
            event = {"type": "error", "error": error, "handled": handled}
        state["active"] = None
        return self.store.save(state, dict(event, token=token, node=node_id))

    def _step(self, state, node, token):
        current = state["stack"][-1]
        node_id = current["pc"]
        scope = current["scope"]
        kind = node["kind"]
        if kind == "call":
            tool_id = resolve(node["tool"], scope)
            if not isinstance(tool_id, str) or tool_id not in state["tools"]:
                raise ValueError(f"unregistered tool: {tool_id}")
            spec = state["tools"][tool_id]
            arguments = resolve(node.get("input", {}), scope)
            check(spec.get("input_schema", {}), arguments)
            if spec["kind"] == "workflow":
                check(spec["workflow"].get("input_schema", {}), arguments)
                state["stack"].append(frame(spec["workflow"], arguments, node_id, spec.get("output_schema", {})))
                return {"type": "workflow_enter", "tool": tool_id}
            context = {"run_id": state["id"], "node_id": node_id, "token": token,
                       "depth": len(state["stack"]), "step": state["steps"]}
            output = invoke(spec, arguments, context, Path(state["artifacts"]) / state["id"] / token)
            store_output(current, node_id, output)
            current["pc"] = node["next"]
            return {"type": "output", "tool": tool_id, "value": output}
        if kind == "branch":
            value = resolve(node["value"], scope)
            key = value if isinstance(value, str) else dumps(value)
            current["pc"] = node["cases"].get(key, node["default"])
            return {"type": "branch", "value": value, "target": current["pc"]}
        if kind == "wait":
            state.update(status="waiting", pending={"id": token, "node": node_id,
                         "question": resolve(node["question"], scope),
                         "answer_schema": node.get("answer_schema", {})})
            return {"type": "waiting", "pending": state["pending"]}
        output = resolve(node.get("value"), scope)
        check(current["flow"].get("output_schema", {}), output)
        check(current["output_schema"], output)
        finished = state["stack"].pop()
        if state["stack"]:
            parent = state["stack"][-1]
            call_id = finished["parent"]
            store_output(parent, call_id, output)
            parent["pc"] = parent["flow"]["nodes"][call_id]["next"]
        else:
            state.update(status="completed", result=output)
        return {"type": "returned", "value": output}

    def drive(self, run_id, *, max_ticks=100):
        if type(max_ticks) is not int or max_ticks <= 0:
            raise ValueError("max_ticks must be a positive integer")
        state = self.store.load(run_id)
        for _ in range(max_ticks):
            if state["status"] != "ready":
                break
            state = self.tick(run_id)
        return state

    def resume(self, run_id, answer, *, pending_id):
        state = self.store.load(run_id)
        if state["status"] != "waiting" or state["pending"]["id"] != pending_id:
            raise Conflict("answer does not match the current pending question")
        check(state["pending"]["answer_schema"], answer)
        answer = clone(answer)
        current = state["stack"][-1]
        node_id = current["pc"]
        store_output(current, node_id, answer)
        current["pc"] = current["flow"]["nodes"][node_id]["next"]
        state.update(status="ready", pending=None)
        return self.store.save(state, {"type": "answered", "pending_id": pending_id, "value": answer})

    def retry(self, run_id):
        """Explicit opt-in: failed tools can already have produced side effects."""
        state = self.store.load(run_id)
        if state["status"] != "failed" or state["error"]["type"] == "StepLimit":
            raise Conflict("only a failed node below the step limit can be retried")
        state.update(status="ready", error=None)
        return self.store.save(state, {"type": "retry_requested"})

    def recover(self, run_id, *, expected_token):
        """Operator asserts the old executor is stopped. Never automatically replay."""
        state = self.store.load(run_id)
        if state["status"] != "running" or state["active"]["token"] != expected_token:
            raise Conflict("execution token does not match interrupted operation")
        state.update(status="failed", error={"type": "Interrupted", "message": "outcome unknown; inspect effects before retry"}, active=None)
        return self.store.save(state, {"type": "recovered", "token": expected_token})
