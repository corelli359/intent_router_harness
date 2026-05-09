# Tools

Tools are command-backed executors used by the Router runtime. They are not model-visible by default.

## Layout

- `<tool-name>/<semantic-name>_tool.json`: tool metadata and entrypoint.
- `<tool-name>/<semantic-name>.py`: command implementation. The command reads a JSON payload from stdin and writes a JSON object to stdout.

## Current Tools

- `workflow-api-call`: executes workflow `use_as_tool` HTTP POST requests and returns raw SSE text for the Router to parse.
