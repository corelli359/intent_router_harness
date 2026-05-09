from __future__ import annotations

import json
import sys


def handle(payload: dict) -> dict | None:
    phase = payload.get("phase")
    if phase == "message":
        event = payload.get("event") or {}
        additional = event.get("additional_kwargs") if isinstance(event, dict) else {}
        if not isinstance(additional, dict) or "node_output" not in additional:
            raise ValueError("workflow SSE message is missing additional_kwargs.node_output")
        return {
            "status": "waiting_assistant_completion",
            "completion_reason": "workflow_node_output",
            "output": additional["node_output"],
        }
    if phase == "done":
        last = payload.get("last") or {}
        return {
            "status": "completed",
            "completion_reason": "workflow_done",
            "output": last.get("output") if isinstance(last, dict) else None,
        }
    if phase == "error":
        return {
            "status": "failed",
            "completion_reason": "workflow_error",
            "output": {"error": payload.get("error") or {}},
        }
    return None


if __name__ == "__main__":
    result = handle(json.load(sys.stdin))
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
