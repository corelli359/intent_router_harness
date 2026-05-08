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
    workflow_agent_id: str
    app_code: str
    path: str
    method: str = "POST"
    stream: bool = True
    slots_param_name: str = "slots_data"
    slot_schema: dict[str, Any] | None = None
    passthrough_config_variables: tuple[str, ...] = ()


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
        url = _join_url(self.settings.base_url, spec.path)
        raw_body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=raw_body,
            method="POST",
            headers={
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
                workflow_agent_id=str(payload.get("workflow_agent_id") or "").strip(),
                app_code=str(payload.get("app_code") or "").strip(),
                path=str(payload.get("path") or "").strip(),
                method=str(payload.get("method") or "POST").strip() or "POST",
                stream=bool(payload.get("stream", True)),
                slots_param_name=str(payload.get("slots_param_name") or "slots_data").strip()
                or "slots_data",
                slot_schema=payload.get("slot_schema") if isinstance(payload.get("slot_schema"), dict) else None,
                passthrough_config_variables=tuple(
                    _string_list(payload.get("passthrough_config_variables"))
                ),
            )
            if not spec.intent_code or not spec.path:
                raise WorkflowToolError(f"workflow reference {reference.id!r} is missing intent_code or path")
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
    """Build the workflow use_as_tool request from passthrough values and slots."""
    values = _config_variable_map(request.config_variables)
    values.setdefault("custID", request.custID)
    values.setdefault("sessionID", request.sessionId)
    values.setdefault("agentSessionID", request.sessionId)
    values.setdefault("currentDisplay", _current_display_value(request.currentDisplay))

    config_variables: list[dict[str, Any]] = []
    for name in spec.passthrough_config_variables:
        if name in values:
            config_variables.append({"name": name, "value": values[name]})
    if "custID" not in {item["name"] for item in config_variables}:
        config_variables.insert(0, {"name": "custID", "value": request.custID})
    config_variables.append(
        {
            "name": spec.slots_param_name,
            "value": json.dumps(task.slot_memory, ensure_ascii=False),
        }
    )
    return {
        "session_id": request.sessionId,
        "txt": request.txt,
        "stream": spec.stream,
        "config_variables": config_variables,
    }


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


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."
