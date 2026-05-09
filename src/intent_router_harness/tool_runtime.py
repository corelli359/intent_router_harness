from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


class ToolRuntimeError(RuntimeError):
    """Raised when a configured tool cannot run."""


@dataclass(frozen=True, slots=True)
class CommandTool:
    """One command-backed tool loaded from the tools directory."""

    name: str
    entrypoint: Path
    cwd: Path

    def run(self, payload: dict[str, Any], *, timeout_seconds: float = 60.0) -> dict[str, Any]:
        command = (sys.executable, str(self.entrypoint))
        completed = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            cwd=self.cwd,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise ToolRuntimeError(f"tool {self.name!r} exited {completed.returncode}: {message}")
        try:
            result = json.loads(completed.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ToolRuntimeError(f"tool {self.name!r} stdout is not JSON") from exc
        if not isinstance(result, dict):
            raise ToolRuntimeError(f"tool {self.name!r} stdout must be a JSON object")
        return result


def load_command_tools(roots: list[str | Path]) -> dict[str, CommandTool]:
    """Load command-backed tools from configured roots."""
    tools: dict[str, CommandTool] = {}
    for root in roots:
        root_path = Path(root).expanduser()
        if not root_path.is_dir():
            continue
        for tool_dir in sorted(item for item in root_path.iterdir() if item.is_dir()):
            config_path = _tool_config_path(tool_dir)
            if config_path is None:
                continue
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ToolRuntimeError(f"{config_path} must contain a JSON object")
            name = str(payload.get("name") or tool_dir.name)
            entrypoint = str(payload.get("entrypoint") or "")
            if not entrypoint:
                raise ToolRuntimeError(f"tool {name!r} must define entrypoint")
            entrypoint_path = Path(entrypoint)
            if not entrypoint_path.is_absolute():
                entrypoint_path = tool_dir / entrypoint_path
            if not entrypoint_path.is_file():
                raise ToolRuntimeError(f"tool {name!r} entrypoint does not exist: {entrypoint_path}")
            tools[name] = CommandTool(name=name, entrypoint=entrypoint_path.resolve(), cwd=tool_dir)
    return tools


def _tool_config_path(tool_dir: Path) -> Path | None:
    configs = sorted(tool_dir.glob("*tool.json"))
    if not configs:
        return None
    if len(configs) > 1:
        raise ToolRuntimeError(f"tool {tool_dir.name!r} has multiple *tool.json configs")
    return configs[0]
