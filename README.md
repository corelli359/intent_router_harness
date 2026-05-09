# intent_router_harness

`intent_router_harness` is a standalone assistant-protocol router for intent
recognition, serial business task queues, skill-constrained slot filling, and
task completion callbacks.

It does not import, patch, or configure any production router project. The
project owns its own specs, skills, regression data, tests, and local service.

## Core Model

- `agent.md` is loaded as the root instruction layer.
- The first LLM call performs intent recognition and multi-intent splitting
  using only skill `name`, `description`, and `intent_codes`.
- The service owns `task_list` ordering and chooses one `current_task`.
- The second LLM call loads only the current task's `SKILL.md` body and fills
  only that task's slots.
- Skill frontmatter declares one `intent_code` and its `required_slots`.
- The service computes `waiting_user_input` or `ready_for_dispatch` from
  `required_slots`; LLM output is not the source of truth for task readiness.
- Skill and reference bodies are not stored in session state.

## Layout

- `src/intent_router_harness`: router runtime, service, session, LLM, and skill loading code.
- `examples`: sample service specs, mock servers, and local clients.
- `hooks`: workflow tool lifecycle hooks. Hook commands are runtime-only and never rendered into prompts.
- `tools`: command-backed runtime tools, including workflow API execution.
- `regressions`: structured regression suites.
- `skills`: sample business skills and references.
- `tests`: pytest coverage for service behavior and protocol rules.

## Commands

```bash
python -m pytest -q
PYTHONPATH=src python -m intent_router_harness show-suite regressions/assistant_protocol_v0_6.json
PYTHONPATH=src python -m intent_router_harness llm-smoke --env-file .env.local
PYTHONPATH=src python -m intent_router_harness serve examples/finance-router-harness.toml --port 8765
PYTHONPATH=src python -m intent_router_harness serve-asgi --host 0.0.0.0 --port 8765
python examples/mock_workflow_server.py --host 127.0.0.1 --port 9876
python examples/router_message_client.py --base-url http://127.0.0.1:8765 --execution-mode execute --txt '给陈广荣转500元'
```

After installing the package, the same commands are available through
`intent-router-harness`.

## HTTP Service

- `GET /healthz`: liveness check.
- `GET /readyz`: readiness check and LLM configuration visibility.
- `GET /` or `/validator`: browser validation UI.
- `POST /api/v1/message`: assistant protocol message entrypoint.
- `POST /api/v1/task/completion`: task completion callback.

```bash
curl -s http://127.0.0.1:8765/api/v1/message \
  -H 'Content-Type: application/json' \
  -d '{
    "sessionId": "assistant_demo_001",
    "custID": "C0001",
    "txt": "给小明转账200元",
    "stream": true,
    "executionMode": "router_only"
  }'
```
