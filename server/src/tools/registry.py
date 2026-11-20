"""Typed tool registry: name + JSON Schema + async handler + one-line summary; emits timeline events."""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from events import hub

logger = logging.getLogger("arogya.tools")


@dataclass
class ToolContext:
    session_id: str
    patient_id: str = "anon"
    lang: str = "hi-IN"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Awaitable[dict]]
    summary: Callable[[dict], str] = lambda r: "done"

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.parameters}}


REGISTRY: Dict[str, Tool] = {}


def tool(name: str, description: str, parameters: Optional[dict] = None, summary=None):
    def deco(fn):
        REGISTRY[name] = Tool(name, description,
                              parameters or {"type": "object", "properties": {}},
                              fn, summary or (lambda r: "done"))
        return fn
    return deco


def schemas() -> List[dict]:
    return [t.schema() for t in REGISTRY.values()]


async def run_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    t = REGISTRY.get(name)
    if t is None:
        return {"ok": False, "error": f"unknown tool {name}"}
    hub.publish(ctx.session_id, {"type": "tool_start", "tool": name, "args": args})
    t0 = time.perf_counter()
    ok = True
    try:
        result = await t.handler(ctx, **args)
        ok = result.get("ok", True) is not False
    except TypeError as e:  # bad args from the model
        result, ok = {"ok": False, "error": f"bad arguments: {e}"}, False
    except Exception as e:  # never let a tool crash the voice turn
        logger.exception("tool %s failed", name)
        result, ok = {"ok": False, "error": f"{type(e).__name__}: {e}"}, False
    ms = (time.perf_counter() - t0) * 1000
    try:
        summary = t.summary(result)
    except Exception:
        summary = "done" if ok else str(result.get("error", "failed"))
    logger.info(json.dumps({"tool": name, "ms": round(ms), "ok": ok}))
    hub.publish(ctx.session_id, {"type": "tool_end", "tool": name, "args": args, "summary": summary,
                                 "ms": round(ms), "ok": ok, "result": result})
    return result
