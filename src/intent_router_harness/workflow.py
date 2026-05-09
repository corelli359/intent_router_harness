from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

from intent_router_harness.contracts import ConfigVariable, PlannedTask, RouterMessageRequest
from intent_router_harness.llm import load_env_file
from intent_router_harness.skills import SkillLibrary


class WorkflowToolError(RuntimeError):
    """Raised when a workflow tool call fails or returns an invalid stream."""


@dataclass(frozen=True, slots=True)
class WorkflowToolSpec:
    """Machine-readable contract for one workflow tool."""

    intent_code: str
    url: str
    method: str = "POST"
    headers: dict[str, str] | None = None
    body: Any = None
    workflow_agent_id: str = ""
    app_code: str = ""


@dataclass(frozen=True, slots=True)
class WorkflowToolEvent:
    """One workflow SSE message reduced to node metadata."""

    node_id: str | None
    node_title: str | None
    timestamp: str | None
    node_output: Any


@dataclass(frozen=True, slots=True)
class WorkflowToolResult:
    """Workflow call result used to emit assistant protocol frames."""

    events: tuple[WorkflowToolEvent, ...]

    @property
    def final_output(self) -> Any:
        if not self.events:
            return {}
        return self.events[-1].node_output


@dataclass(frozen=True, slots=True)
class WorkflowSettings:
    """HTTP settings for workflow tool calls."""

    base_url: str
    timeout_seconds: float = 60.0


class WorkflowToolClient(Protocol):
    """Boundary for invoking workflow tools."""

    def run_workflow(
        self,
        spec: WorkflowToolSpec,
        *,
        request_payload: dict[str, Any],
    ) -> WorkflowToolResult:
        """Invoke a workflow tool and return parsed node outputs."""


def load_workflow_settings(env_file: str | Path = ".env.local") -> WorkflowSettings | None:
    """Load optional workflow HTTP settings from env and a dotenv file."""
    file_values = load_env_file(env_file)

    def get(name: str) -> str | None:
        return os.getenv(name) or file_values.get(name)

    base_url = get("ROUTER_WORKFLOW_BASE_URL")
    if not base_url:
        return None
    return WorkflowSettings(
        base_url=base_url,
        timeout_seconds=float(get("ROUTER_WORKFLOW_TIMEOUT_SECONDS") or "60"),
    )


class HTTPWorkflowToolClient:
    """Small synchronous SSE client for workflow use_as_tool endpoints."""

    def __init__(self, settings: WorkflowSettings) -> None:
        self.settings = settings

    def run_workflow(
        self,
        spec: WorkflowToolSpec,
        *,
        request_payload: dict[str, Any],
    ) -> WorkflowToolResult:
        if spec.method.upper() != "POST":
            raise WorkflowToolError(f"unsupported workflow method: {spec.method}")
        url = _join_url(self.settings.base_url, spec.url)
        raw_body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=raw_body,
            method="POST",
            headers=spec.headers or {
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                sse_text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise WorkflowToolError(f"HTTP {exc.code} from workflow: {_truncate(raw_error, 300)}") from exc
        except error.URLError as exc:
            raise WorkflowToolError(f"workflow request failed: {exc.reason}") from exc
        return parse_workflow_sse(sse_text)


def load_workflow_tool_specs(skills: SkillLibrary) -> dict[str, WorkflowToolSpec]:
    """Load workflow tool specs from skill-owned machine-readable references."""
    specs: dict[str, WorkflowToolSpec] = {}
    for skill_name in skills.names():
        skill = skills.get(skill_name)
        if skill is None:
            continue
        for reference in skill.references:
            payload = _workflow_reference_payload(reference.body)
            if payload is None:
                continue
            spec = WorkflowToolSpec(
                intent_code=str(payload.get("intent_code") or "").strip(),
                url=str(payload.get("url") or payload.get("path") or "").strip(),
                method=str(payload.get("method") or "POST").strip() or "POST",
                headers=_string_dict(payload.get("headers")),
                body=payload.get("body"),
                workflow_agent_id=str(payload.get("workflow_agent_id") or "").strip(),
                app_code=str(payload.get("app_code") or "").strip(),
            )
            if not spec.intent_code or not spec.url:
                raise WorkflowToolError(f"workflow reference {reference.id!r} is missing intent_code or url")
            specs[spec.intent_code] = spec
    return specs


def is_workflow_tool_reference_body(body: str) -> bool:
    """Return whether a reference body is a workflow tool contract."""
    return _workflow_reference_payload(body) is not None


def build_workflow_request_payload(
    spec: WorkflowToolSpec,
    *,
    request: RouterMessageRequest,
    task: PlannedTask,
) -> dict[str, Any]:
    """Render the workflow HTTP body template from request, config variables, and slots."""
    if spec.body is not None:
        rendered = _render_template(spec.body, request=request, task=task)
        if not isinstance(rendered, dict):
            raise WorkflowToolError("workflow body template must render to a JSON object")
        return rendered
    return _legacy_workflow_request_payload(request=request, task=task)


def parse_workflow_sse(text: str) -> WorkflowToolResult:
    """Parse workflow SSE text and extract every message node_output as a whole."""
    events: list[WorkflowToolEvent] = []
    saw_done = False
    for event_name, raw_data in _iter_sse_events(text):
        if event_name == "done" or raw_data == "[DONE]":
            saw_done = True
            continue
        if event_name != "message":
            continue
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise WorkflowToolError(f"workflow SSE data is not JSON: {exc}") from exc
        additional = payload.get("additional_kwargs")
        if not isinstance(additional, dict) or "node_output" not in additional:
            raise WorkflowToolError("workflow SSE message is missing additional_kwargs.node_output")
        events.append(
            WorkflowToolEvent(
                node_id=_optional_string(additional.get("node_id")),
                node_title=_optional_string(additional.get("node_title")),
                timestamp=_optional_string(additional.get("timestamp")),
                node_output=additional.get("node_output"),
            )
        )
    if not saw_done:
        raise WorkflowToolError("workflow SSE stream ended without done event")
    return WorkflowToolResult(events=tuple(events))


def workflow_event_output(event: WorkflowToolEvent) -> Any:
    """Return the assistant frame output for one workflow event."""
    return event.node_output


def _workflow_reference_payload(body: str) -> dict[str, Any] | None:
    stripped = body.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("type") != "workflow_tool":
        return None
    return payload


def _render_template(value: Any, *, request: RouterMessageRequest, task: PlannedTask) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _render_template(item, request=request, task=task)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_render_template(item, request=request, task=task) for item in value]
    if isinstance(value, str) and value.startswith("$") and value.count("$") == 1:
        return _resolve_template_variable(value[1:], request=request, task=task)
    return value


def _resolve_template_variable(name: str, *, request: RouterMessageRequest, task: PlannedTask) -> Any:
    config = _config_variable_map(request.config_variables)
    variables: dict[str, Any] = {
        "sessionId": request.sessionId,
        "txt": request.txt,
        "custID": request.custID,
        "currentDisplay": _current_display_value(request.currentDisplay),
        "stream": request.stream,
        "config": config,
        "slot_memory": task.slot_memory,
        "slot_memory_json": json.dumps(task.slot_memory, ensure_ascii=False),
        "slots": task.slot_memory,
        "slots_json": json.dumps(task.slot_memory, ensure_ascii=False),
    }
    if name in variables:
        return variables[name]
    if name.startswith("config."):
        return config.get(name.removeprefix("config."), "")
    if name.startswith("slot."):
        return _nested_lookup(task.slot_memory, name.removeprefix("slot."))
    raise WorkflowToolError(f"unknown workflow template variable: ${name}")


def _nested_lookup(values: dict[str, Any], path: str) -> Any:
    current: Any = values
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _legacy_workflow_request_payload(
    *,
    request: RouterMessageRequest,
    task: PlannedTask,
) -> dict[str, Any]:
    values = _config_variable_map(request.config_variables)
    values.setdefault("custID", request.custID)
    values.setdefault("sessionID", request.sessionId)
    values.setdefault("agentSessionID", request.sessionId)
    values.setdefault("currentDisplay", _current_display_value(request.currentDisplay))
    return {
        "session_id": request.sessionId,
        "txt": request.txt,
        "stream": True,
        "config_variables": [
            {"name": "custID", "value": values.get("custID", request.custID)},
            {"name": "sessionID", "value": values.get("sessionID", request.sessionId)},
            {"name": "currentDisplay", "value": values.get("currentDisplay", "")},
            {"name": "agentSessionID", "value": values.get("agentSessionID", request.sessionId)},
            {"name": "slots_data", "value": json.dumps(task.slot_memory, ensure_ascii=False)},
        ],
    }


def _iter_sse_events(text: str):
    normalized = text.replace("\r\n", "\n")
    for raw_frame in normalized.split("\n\n"):
        if not raw_frame.strip():
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in raw_frame.split("\n"):
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").lstrip())
        yield event_name, "\n".join(data_lines)


def _config_variable_map(items: list[ConfigVariable]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for item in items:
        values[item.name] = item.value
    return values


def _current_display_value(current_display: list[dict[str, Any]]) -> str:
    if not current_display:
        return ""
    return json.dumps(current_display, ensure_ascii=False)


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list | tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _string_dict(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."
