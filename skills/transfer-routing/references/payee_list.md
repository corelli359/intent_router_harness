# 已知收款人列表获取

## 请求地址

```text
http://aiml-pub.aisp.test.abc/agent-api/workflow-agent-1-5556936d/chatabc/use_as_tool
```

## 请求参数

```json
{
  "session_id": "1234",
  "txt": "已知收款人有哪些？",
  "config_variables": []
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
curl -X POST "http://aiml-pub.aisp.test.abc/agent-api/workflow-agent-1-5556936d/chatabc/use_as_tool" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "1234",
    "txt": "已知收款人有哪些？",
    "config_variables": []
  }'
```

## 说明

- 用于查询当前上下文中可直接使用的已知收款人列表
- `session_id`：会话标识
- `txt`：固定传“已知收款人有哪些？”即可
- `config_variables`：此接口场景下传空数组
