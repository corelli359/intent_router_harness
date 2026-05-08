from __future__ import annotations

import pytest

from intent_router_harness.workflow import WorkflowToolError, parse_workflow_sse


def test_parse_workflow_sse_extracts_node_output_as_whole() -> None:
    result = parse_workflow_sse(
        "\n".join(
            [
                "event:message",
                'data:{"additional_kwargs":{"node_id":"start","node_title":"开始","node_output":{"a":1},"timestamp":"t1"}}',
                "",
                "event:message",
                'data:{"additional_kwargs":{"node_id":"end","node_title":"结束","node_output":["opaque",2],"timestamp":"t2"}}',
                "",
                "event:done",
                "data:[DONE]",
                "",
            ]
        )
    )

    assert [event.node_output for event in result.events] == [{"a": 1}, ["opaque", 2]]
    assert result.final_output == ["opaque", 2]


def test_parse_workflow_sse_rejects_non_json_message() -> None:
    with pytest.raises(WorkflowToolError, match="not JSON"):
        parse_workflow_sse(
            "\n".join(
                [
                    "event:message",
                    "data:not-json",
                    "",
                    "event:done",
                    "data:[DONE]",
                    "",
                ]
            )
        )


def test_parse_workflow_sse_rejects_missing_node_output() -> None:
    with pytest.raises(WorkflowToolError, match="node_output"):
        parse_workflow_sse(
            "\n".join(
                [
                    "event:message",
                    'data:{"additional_kwargs":{"node_id":"end"}}',
                    "",
                    "event:done",
                    "data:[DONE]",
                    "",
                ]
            )
        )


def test_parse_workflow_sse_requires_done_event() -> None:
    with pytest.raises(WorkflowToolError, match="without done"):
        parse_workflow_sse(
            "\n".join(
                [
                    "event:message",
                    'data:{"additional_kwargs":{"node_output":{}}}',
                    "",
                ]
            )
        )
