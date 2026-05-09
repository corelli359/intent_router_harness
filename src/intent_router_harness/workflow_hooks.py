from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


class WorkflowHookError(RuntimeError):
    """Raised when a workflow tool hook command fails."""


@dataclass(frozen=True, slots=True)
class WorkflowHook:
    """One command hook loaded for workflow tool lifecycle events."""

    name: str
    events: tuple[str, ...]
    command: tuple[str, ...]
    cwd: Path


def load_workflow_hooks(roots: list[str | Path]) -> tuple[WorkflowHook, ...]:
    """Load hooks from configured roots.

    A root has a top-level hooks.json with a hooks array of enabled hook
    directory names. Each hook directory contains one semantic *hook.json
    config file and a handler script.
    """
    hooks: list[WorkflowHook] = []
    for root in roots:
        root_path = Path(root).expanduser()
        root_config = root_path if root_path.is_file() else root_path / "hooks.json"
        if not root_config.is_file():
            continue
        payload = json.loads(root_config.read_text(encoding="utf-8"))
        raw_enabled = payload.get("hooks") if isinstance(payload, dict) else None
        if not isinstance(raw_enabled, list):
            raise WorkflowHookError(f"{root_config} must contain a hooks array")
        for index, raw_item in enumerate(raw_enabled):
            if isinstance(raw_item, str):
                hook_dir = root_config.parent / raw_item
                hook_config = _hook_config_path(hook_dir)
                raw_hook = json.loads(hook_config.read_text(encoding="utf-8"))
                if not isinstance(raw_hook, dict):
                    raise WorkflowHookError(f"{hook_config} must contain a hook object")
                hooks.append(_parse_hook(raw_hook, cwd=hook_dir, index=index))
                continue
            if isinstance(raw_item, dict):
                hooks.append(_parse_hook(raw_item, cwd=root_config.parent, index=index))
                continue
            raise WorkflowHookError(f"{root_config} hook #{index + 1} must be a directory name or object")
    return tuple(hooks)


def _hook_config_path(hook_dir: Path) -> Path:
    configs = sorted(hook_dir.glob("*hook.json"))
    if not configs:
        raise WorkflowHookError(f"enabled hook {hook_dir.name!r} is missing a *hook.json config")
    if len(configs) > 1:
        raise WorkflowHookError(f"enabled hook {hook_dir.name!r} has multiple *hook.json configs")
    return configs[0]


def run_first_workflow_hook(
    hooks: tuple[WorkflowHook, ...],
    *,
    event: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Run the first command hook for one workflow tool lifecycle event."""
    for hook in hooks:
        if event not in hook.events:
            continue
        result = _run_hook_command(hook, payload=payload)
        if result is not None:
            return result
    return None


def run_workflow_hooks(
    hooks: tuple[WorkflowHook, ...],
    *,
    event: str,
    payload: dict[str, Any],
) -> None:
    """Run all command hooks for one workflow tool lifecycle event."""
    for hook in hooks:
        if event not in hook.events:
            continue
        _run_hook_command(hook, payload=payload)


def _parse_hook(raw_hook: dict[str, Any], *, cwd: Path, index: int) -> WorkflowHook:
    name = str(raw_hook.get("name") or f"hook_{index + 1}")
    raw_events = raw_hook.get("events")
    if isinstance(raw_events, str):
        events = (raw_events,)
    elif isinstance(raw_events, list):
        events = tuple(str(item) for item in raw_events if str(item).strip())
    else:
        events = ()
    if not events:
        raise WorkflowHookError(f"hook {name!r} must define events")
    raw_command = raw_hook.get("command")
    if isinstance(raw_command, str):
        command = (raw_command,)
    elif isinstance(raw_command, list):
        command = tuple(str(item) for item in raw_command)
    else:
        command = ()
    if not command:
        raise WorkflowHookError(f"hook {name!r} must define command")
    return WorkflowHook(name=name, events=events, command=command, cwd=cwd)


def _run_hook_command(hook: WorkflowHook, *, payload: dict[str, Any]) -> dict[str, Any] | None:
    command = _resolve_command(hook.command, cwd=hook.cwd)
    completed = subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=hook.cwd,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise WorkflowHookError(f"workflow hook {hook.name!r} exited {completed.returncode}: {message}")
    stdout = completed.stdout.strip()
    if not stdout:
        return None
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowHookError(f"workflow hook {hook.name!r} stdout is not JSON") from exc
    if not isinstance(result, dict):
        raise WorkflowHookError(f"workflow hook {hook.name!r} stdout must be a JSON object")
    return result


def _resolve_command(command: tuple[str, ...], *, cwd: Path) -> tuple[str, ...]:
    if command[0] in {"python", "python3"}:
        resolved = [sys.executable, *command[1:]]
    else:
        resolved = list(command)
    if len(resolved) > 1 and resolved[1].endswith(".py"):
        script = Path(resolved[1])
        if not script.is_absolute():
            resolved[1] = str((cwd / script).resolve())
    return tuple(resolved)

