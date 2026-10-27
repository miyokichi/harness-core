"""Agent policy implemented entirely as ordinary registered functions and a flow."""
from . import knowledge
from .llm import complete
from .registry import Registry, check
from .values import clone, dumps


def obj(properties, required):
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


TEXT = {"type": "string", "minLength": 1}
DECISION = {"oneOf": [
    obj({"action": {"const": "execute"}, "tool": TEXT, "arguments": {"type": "object"}}, ["action", "tool", "arguments"]),
    obj({"action": {"const": "ask"}, "question": TEXT, "missing": TEXT}, ["action", "question", "missing"]),
    obj({"action": {"const": "finish"}, "result": {}, "evidence": TEXT}, ["action", "result", "evidence"])]}


def initialize(request):
    return {"request": request, "observations": [], "answers": []}


def decide(state, config, tools):
    catalog = {k: {f: v.get(f, {}) for f in ("description", "input_schema", "output_schema")}
               for k, v in tools.items()}
    known = []
    for requirement in state["request"].get("knowledge", []):
        known.append(knowledge.assess(**requirement))
    value = complete(config, [
        {"role": "system", "content": "Choose execute, ask, finish. Ask for missing conditions; never infer units. "
         "Use only listed tools. Saved human rules are evidence; hypotheses are not. Return JSON: " + dumps(DECISION)},
        {"role": "user", "content": dumps({"state": state, "tools": catalog, "knowledge": known})}], DECISION)
    if value["action"] == "execute":
        if value["tool"] not in tools:
            raise ValueError("decision selected a non-public tool")
        check(tools[value["tool"]].get("input_schema", {}), value["arguments"])
    return value


def observe(state, observation):
    return dict(state, observations=state["observations"] + [observation])


def learn(state, answer):
    # Only explicitly designated requirements become saved knowledge.
    if "knowledge" in answer:
        record = answer["knowledge"]
        allowed = state["request"].get("knowledge", [])
        target = next((r for r in allowed if r["scope"] == record["scope"] and r["key"] == record["key"]), None)
        if target is None:
            raise ValueError("answer knowledge is outside requested scope/key")
        knowledge.remember(target["database"], record["scope"], record["key"],
                           record["value"], {"kind": "human", "reference": "explicit CLI answer"},
                           record.get("exceptions", []))
    return dict(state, answers=state["answers"] + [answer])


def verify(state, decision, verifier):
    from .registry import load_entry
    report = load_entry(verifier)(state=state, result=decision["result"])
    check(obj({"status": {"enum": ["pass", "fail", "unknown"]}, "checks": {"type": "array"}}, ["status", "checks"]), report)
    if report["status"] != "pass":
        raise ValueError("completion verification: " + report["status"])
    return {"result": decision["result"], "evidence": decision["evidence"], "verification": report}


def invalid():
    raise ValueError("invalid action")


def build(config, business, verifier, checked=False):
    """Freeze the public allowlist in the decision Workflow, separate from internals."""
    business = Registry(business).snapshot()
    if any(k.startswith("agent.") for k in business):
        raise ValueError("agent.* is reserved for internal tools")
    registry = Registry(business)
    for name in ("initialize", "observe", "learn", "invalid", "verify", "decide"):
        registry.register("agent." + name, {"kind": "python", "entry": "seed_harness.agent:" + name})
    ref = lambda p: {"$ref": p}
    nodes = {
        "initialize": {"kind": "call", "tool": "agent.initialize", "input": {"request": ref("input")}, "save_as": "agent", "next": "decide"},
        "decide": {"kind": "call", "tool": "agent.decide", "input": {"state": ref("vars.agent"), "config": config, "tools": business}, "next": "route"},
        "route": {"kind": "branch", "value": ref("steps.decide.action"), "cases": {"execute": "execute", "ask": "ask", "finish": "verify"}, "default": "invalid"},
        "execute": {"kind": "call", "tool": ref("steps.decide.tool"), "input": ref("steps.decide.arguments"), "next": "observe"},
        "observe": {"kind": "call", "tool": "agent.observe", "input": {"state": ref("vars.agent"), "observation": ref("steps.execute")}, "save_as": "agent", "next": "decide"},
        "ask": {"kind": "wait", "question": ref("steps.decide.question"), "answer_schema": {"type": "object"}, "next": "learn"},
        "learn": {"kind": "call", "tool": "agent.learn", "input": {"state": ref("vars.agent"), "answer": ref("steps.ask")}, "save_as": "agent", "next": "decide"},
        "verify": {"kind": "call", "tool": "agent.verify", "input": {"state": ref("vars.agent"), "decision": ref("steps.decide"), "verifier": verifier}, "next": "finish"},
        "finish": {"kind": "return", "value": ref("steps.verify")},
        "invalid": {"kind": "call", "tool": "agent.invalid", "next": "finish"}}
    if checked:
        nodes["observe"]["next"] = "check_observation"
        nodes["check_observation"] = {"kind": "call", "tool": "agent.verify", "input": {
            "state": ref("vars.agent"), "decision": {"result": ref("steps.execute"), "evidence": "post-tool validation"},
            "verifier": verifier}, "next": "decide"}
    return registry, {"schema_version": 1, "id": "agent-loop.v2" if checked else "agent-loop.v1", "entry": "initialize", "nodes": nodes}
