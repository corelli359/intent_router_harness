# Workflow Hooks

Hooks are project-level workflow tool lifecycle handlers. They are not rendered into model prompts.

## Layout

- `hooks.json`: enabled hook directories, in execution order.
- `<hook-name>/<semantic-name>_hook.json`: hook metadata, including events and command.
- `<hook-name>/<semantic-name>.py`: command implementation. The command reads a JSON payload from stdin and may write a JSON object to stdout.

## Events

- `before_workflow_tool_call`: runs before the workflow tool sends the HTTP request.
- `after_workflow_tool_call`: runs after workflow SSE events are parsed and mapped.

Hooks do not use a runtime `match` field. If a hook needs conditional behavior, keep that logic inside its command script.
