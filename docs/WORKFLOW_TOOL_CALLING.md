# Workflow 子工作流调用规范

本文定义 Router 调用子工作流的通用接口规范。该规范适用于转账、缴费、查询等通过 workflow `use_as_tool` 形式接入的子工作流。

## 1. 调用边界

整体链路：

```text
前端 -> Router /api/v1/message
Router -> LLM planner 只提取 slots
Router -> workflow use_as_tool
workflow -> Router SSE node_output
Router -> 前端 SSE output
```

关键约束：

- 模型只负责识别意图和填写 `slot_memory`。
- 除 slots 外，workflow 所需参数全部由前端透传或 Router 会话字段提供。
- 前端透传参数不进入模型 prompt。
- workflow 调用方式由 skill reference 定义。
- Router 不展开、不校验、不理解 `node_output` 内部业务结构。
- Router 返回给前端时，直接令 `output = workflow_event.additional_kwargs.node_output`。

## 2. 前端调用 Router

前端仍调用现有 Router 接口：

```http
POST /api/v1/message
Content-Type: application/json
Accept: text/event-stream
```

请求示例：

```json
{
  "sessionId": "1635501196813426",
  "custID": "1631102265490929",
  "txt": "给陈广荣转500元",
  "stream": true,
  "executionMode": "execute",
  "config_variables": [
    { "name": "sessionID", "value": "1635501196813426" },
    { "name": "currentDisplay", "value": "" },
    { "name": "agentSessionID", "value": "1635501196813426" }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `sessionId` | 是 | Router 会话 ID，也用于 workflow `session_id`。 |
| `custID` | 是 | 客户 ID，会透传给 workflow。 |
| `txt` | 是 | 用户输入，进入模型用于提槽，也透传给 workflow。 |
| `stream` | 否 | 建议传 `true`，返回 SSE。 |
| `executionMode` | 否 | `router_only` 只规划；`execute` 槽齐后调用 workflow。 |
| `config_variables` | 否 | 前端透传参数，不进入模型 prompt。 |

`executionMode` 语义：

| 值 | 行为 |
| --- | --- |
| `router_only` | 只做意图识别、提槽和任务规划；槽齐返回 `ready_for_dispatch`，不调用 workflow。 |
| `execute` | 槽齐后调用对应 workflow，并把 workflow `node_output` 流式返回。 |

## 3. Skill 与 Reference 分层

建议每个场景按三层拆分：

```text
SKILL.md                意图路由/场景边界，模型在意图识别阶段使用。
references/slot_filling.md   提槽业务规则，模型在提槽阶段默认加载。
references/workflow_tool.json Router 执行期 HTTP 请求模板，模型不可见。
```

`SKILL.md` 的 references 示例：

```json
[
  { "id": "slot_filling", "path": "references/slot_filling.md", "purpose": "转账提槽规则" },
  { "id": "payee_list", "path": "references/payee_list.md", "purpose": "已知收款人列表查询接口说明" },
  { "id": "workflow_tool", "path": "references/workflow_tool.json", "purpose": "转账子工作流 HTTP 请求模板，仅供 Router 执行阶段读取" }
]
```

加载规则：

- 意图识别阶段只使用 skill metadata 和轻量正文。
- 提槽阶段自动加载 `slot_filling` reference。
- 模型仍可通过 `requested_references` 请求额外 reference，例如 `payee_list`。
- `workflow_tool.json` 永远不进入模型 prompt，只供 Router 执行阶段读取。

## 4. Workflow HTTP 模板

每个可执行子工作流通过 `workflow_tool.json` 声明 HTTP 请求模板。模板本身保持最终请求结构，只在动态字段使用 `$变量`。示例：

```json
{
  "type": "workflow_tool",
  "intent_code": "AG_TRANS",
  "method": "POST",
  "url": "/agent-api/workflow-agent-1-1b14f16b/chatabc/use_as_tool",
  "headers": {
    "Accept": "text/event-stream",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json"
  },
  "body": {
    "session_id": "$sessionId",
    "txt": "$txt",
    "stream": true,
    "config_variables": [
      { "name": "custID", "value": "$custID" },
      { "name": "sessionID", "value": "$sessionId" },
      { "name": "currentDisplay", "value": "$config.currentDisplay" },
      { "name": "agentSessionID", "value": "$sessionId" },
      { "name": "slots_data", "value": "$slot_memory_json" }
    ]
  }
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `type` | 固定为 `workflow_tool`。 |
| `intent_code` | 该 workflow 对应的 Router 意图码。 |
| `url` | workflow `use_as_tool` 路径，会拼接到 `ROUTER_WORKFLOW_BASE_URL` 后。 |
| `method` | 当前支持 `POST`。 |
| `headers` | workflow HTTP 请求头。 |
| `body` | workflow HTTP 请求体模板。 |

注意：

- workflow reference 是 Router 执行契约，不作为普通 reference 正文注入模型 prompt。
- 模型可见的是 `slot_filling.md` 等业务 reference，不可见 workflow URL、headers、透传参数等执行细节。
- 模板变量只在整个字符串是 `$变量` 时替换，不支持字符串中间插值。

可用模板变量：

| 变量 | 含义 |
| --- | --- |
| `$sessionId` | Router 请求 `sessionId`。 |
| `$txt` | Router 请求 `txt`。 |
| `$custID` | Router 请求 `custID`。 |
| `$currentDisplay` | Router 请求 `currentDisplay` 序列化结果；为空时是空字符串。 |
| `$config` | 前端 `config_variables` 组装成的对象。 |
| `$config.xxx` | 前端 `config_variables` 中 `name=xxx` 的值；缺省为空字符串。 |
| `$slot_memory` | 当前任务完整 `slot_memory` 对象。 |
| `$slot_memory_json` | 当前任务 `slot_memory` 的 JSON 字符串。 |
| `$slot.xxx` | 当前任务单个槽位。 |

## 5. Router 调用 Workflow

当 planner 输出当前任务：

```json
{
  "intent_code": "AG_TRANS",
  "status": "ready_for_dispatch",
  "slot_memory": {
    "payee_name": "陈广荣",
    "amount": "500"
  }
}
```

且请求为：

```json
{
  "executionMode": "execute"
}
```

Router 根据 workflow reference 渲染内部请求：

```http
POST {ROUTER_WORKFLOW_BASE_URL}/agent-api/workflow-agent-1-1b14f16b/chatabc/use_as_tool
Accept: text/event-stream
Cache-Control: no-cache
Content-Type: application/json
```

请求体：

```json
{
  "session_id": "1635501196813426",
  "txt": "给陈广荣转500元",
  "stream": true,
  "config_variables": [
    { "name": "custID", "value": "1631102265490929" },
    { "name": "sessionID", "value": "1635501196813426" },
    { "name": "currentDisplay", "value": "" },
    { "name": "agentSessionID", "value": "1635501196813426" },
    { "name": "slots_data", "value": "{\"payee_name\":\"陈广荣\",\"amount\":\"500\"}" }
  ]
}
```

配置：

```bash
ROUTER_WORKFLOW_BASE_URL=http://aiml-pub.aisp.test.abc
ROUTER_WORKFLOW_TIMEOUT_SECONDS=60
```

## 6. Workflow SSE 响应

workflow 返回 SSE：

```text
event:message
data:{...}

event:message
data:{...}

event:done
data:[DONE]
```

单个 message 示例：

```json
{
  "content": "",
  "additional_kwargs": {
    "node_id": "end",
    "node_title": "结束",
    "node_output": {
      "output": "...",
      "exception": null
    },
    "timestamp": "2026-05-08 19:19:04.553"
  },
  "response_metadata": {},
  "type": "ai",
  "name": null,
  "id": null,
  "tool_calls": [],
  "invalid_tool_calls": [],
  "usage_metadata": null
}
```

Router 只读取：

```text
data.additional_kwargs.node_output
```

不解析：

```text
node_output.output
node_output.result
node_output.isHandOver
node_output.typIntent
node_output.answer
```

## 7. Router SSE 返回映射

workflow 每个 `event:message` 映射为 Router 的一个 `event: message`。

映射规则：

```text
RouterFrame.output = WorkflowMessage.additional_kwargs.node_output
```

示例：

workflow event：

```json
{
  "additional_kwargs": {
    "node_title": "结束",
    "node_output": {
      "output": "...",
      "exception": null
    }
  }
}
```

Router 返回：

```text
event: message
data: {
  "ok": true,
  "status": "waiting_assistant_completion",
  "intent_code": "AG_TRANS",
  "completion_state": 1,
  "completion_reason": "workflow_node_output",
  "output": {
    "output": "...",
    "exception": null
  },
  "slot_memory": {
    "payee_name": "陈广荣",
    "amount": "500"
  }
}
```

workflow 正常 done 后，Router 追加最终完成帧：

```text
event: message
data: {
  "ok": true,
  "status": "completed",
  "intent_code": "AG_TRANS",
  "completion_state": 2,
  "completion_reason": "workflow_done",
  "output": {
    "output": "...",
    "exception": null
  }
}

event: done
data: [DONE]
```

最终完成帧的 `output` 使用最后一个 workflow message 的 `node_output`。

## 8. 异常处理

以下情况视为 workflow 调用失败：

- workflow HTTP 非 2xx。
- workflow SSE 中 `event:message` 的 `data` 不是合法 JSON。
- workflow message 缺少 `additional_kwargs.node_output`。
- workflow SSE 未返回 `event:done` / `data:[DONE]`。
- 请求 workflow 发生网络错误或超时。

失败时 Router 返回：

```json
{
  "ok": false,
  "status": "failed",
  "completion_state": 2,
  "completion_reason": "workflow_error",
  "output": {
    "error": {
      "code": "workflow_error",
      "message": "..."
    }
  }
}
```

## 9. 状态流转

`router_only`：

```text
waiting_user_input -> ready_for_dispatch
```

`execute`：

```text
waiting_user_input -> ready_for_dispatch -> waiting_assistant_completion -> completed
```

规则：

- 槽位缺失：返回 `waiting_user_input`。
- 槽位齐全且 `router_only`：返回 `ready_for_dispatch`，不调用 workflow。
- 槽位齐全且 `execute`：调用 workflow。
- workflow 节点输出中间帧：`waiting_assistant_completion` / `workflow_node_output`。
- workflow 正常结束：`completed` / `workflow_done`。
- workflow 失败：`failed` / `workflow_error`。
