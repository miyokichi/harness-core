"""Deterministic planner fixture. Replace decide() with an LLM adapter."""
from seed_harness import knowledge


def initialize(request):
    return {"request": request, "observations": [], "answer": None}


def decide(state):
    request = state["request"]
    rule = knowledge.lookup(request["knowledge_db"], "demo.dimension", "selection")
    if not rule["found"]:
        return {"action": "ask", "question": "設計値と実測値のどちらを採用しますか？ selection=design または measured"}
    if not state["observations"]:
        return {"action": "execute", "tool": "dimension.pipeline",
                "arguments": {"selection": rule["record"]["value"]}}
    result = state["observations"][-1]
    return {"action": "finish", "result": result}


def observe(state, observation):
    return dict(state, observations=state["observations"] + [observation])


def learn(state, answer):
    if answer.get("selection") not in {"design", "measured"}:
        raise ValueError("selection must be design or measured")
    knowledge.remember(state["request"]["knowledge_db"], "demo.dimension", "selection",
                       answer["selection"], "user answer in dimension demo")
    return dict(state, answer=answer)


def invalid():
    raise ValueError("planner action must be execute, ask, or finish")


def verify_dimension(result, selection):
    """Demo acceptance checks, not a real semiconductor design rule."""
    if result["unit"] != "nm" or result["selected"] != selection:
        raise ValueError("unit or selection does not match the requested result")
    if type(result["value"]) not in (int, float) or result["value"] <= 0:
        raise ValueError("dimension must be a positive number")
    return dict(result, verification={"status": "pass", "checks": ["unit_nm", "requested_selection", "positive_dimension"]})
