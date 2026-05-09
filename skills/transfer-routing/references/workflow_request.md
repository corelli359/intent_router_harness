# 转账子工作流请求组装

当 `AG_TRANS` 当前任务槽位齐全，并且执行模式为 `execute` 时，需要在 JSON 输出中增加 `workflow_request`。

## 工具调用输出契约

`workflow_request` 只包含以下字段：

```json
{
  "method": "POST",
  "url": "http://127.0.0.1:9876/agent-api/workflow-agent-1-1b14f16b/chatabc/use_as_tool",
  "body": {}
}
```

Router 的 workflow 工具只读取 `method`、`url`、`body` 三个字段，并使用运行时内置请求头执行 SSE 调用。

## 请求接口

- method: `POST`
- url: `http://127.0.0.1:9876/agent-api/workflow-agent-1-1b14f16b/chatabc/use_as_tool`

## 请求体

`workflow_request.body` 必须是 JSON object，结构如下：

```json
{
  "session_id": "config_variables 中 sessionID 的值",
  "txt": "用户原始输入",
  "stream": true,
  "config_variables": [
    { "name": "custID", "value": "config_variables 中 custID 的值" },
    { "name": "sessionID", "value": "config_variables 中 sessionID 的值" },
    { "name": "currentDisplay", "value": "config_variables 中 currentDisplay 的值，缺省为空字符串" },
    { "name": "agentSessionID", "value": "config_variables 中 agentSessionID 的值" },
    { "name": "slots_data", "value": "slot_memory 序列化后的 JSON 字符串" }
  ]
}
```

## 约束

- `workflow_request.url` 必须严格使用上面的完整地址。
- `slots_data` 只来自当前任务 `slot_memory`。
