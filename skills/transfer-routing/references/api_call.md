# 转账 API 调用

## 转账请求地址

```text
http://aiml-pub.aisp.test.abc/agent-api/workflow-agent-1-473c0942/chatabc/use_as_tool
```

## 请求参数

```json
{
  "session_id": "1234",
  "txt": "用户输入",
  "config_variables": [
    {
      "name": "dict",
      "value": "transfer技能执行得到的转账要素提取结果"
    }
  ]
}
```

## 请求 Header

```json
{
  "Content-Type": "application/json"
}
```

## curl 调用示例

```bash
curl -X POST "http://aiml-pub.aisp.test.abc/agent-api/workflow-agent-1-473c0942/chatabc/use_as_tool" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "1234",
    "txt": "用户输入",
    "config_variables": [
      {
        "name": "dict",
        "value": "transfer技能执行得到的转账要素提取结果"
      }
    ]
  }'
```

## 说明

- `session_id`：会话标识
- `txt`：用户原始输入
- `config_variables`：转账技能第二阶段得到的要素提取结果
- `dict`：建议传入结构化转账信息，供转账接口执行
