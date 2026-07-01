# 工作流助手 MVP 规格

版本：v0.3  
状态：已实现（ACP Session + 对话规则）  
日期：2026-06-22

## 目标

在工作台右侧提供常驻「工作流助手」，通过自然语言 + `@` 节点提及修改工作流编排；底层使用 **ACP + Session**，结果从 `.aiwf/assist/<session>/draft.json` 读取。

## 范围

### 包含

- **工作流级编辑**：增删改节点、`transitions`、`initial`、工作流元信息
- **ACP Session 跟随 workflow_id**：切换工作流自动切换/创建 session
- **草稿预览 → 确认应用**：读 `summary.md` + `draft.json`，用户点「应用」写入 `editingWorkflow`
- **撤销**（最多 5 步）、**只读 example 自动 clone**
- **节点上下文**：选中节点 + `@node_id` 提及
- **Provider**：`cursor-agent-acp` / `codex-agent-acp`

### 不包含

- 拖拽节点到助手区、自动保存工作流、Skill/Role 编辑、运行期 iterate

## API

`POST /workflows/assist/stream`（SSE）

请求体：

```json
{
  "description": "用户最新一条消息",
  "provider": "cursor-agent-acp",
  "workflow_id": "workflow_123456",
  "session_id": "assist_abc",
  "draft": { "...editingWorkflow" },
  "selected_node_id": "node_1",
  "focus_node_ids": ["node_1"]
}
```

事件：

- `{ type: "session", session_id, chat_id, workflow_id }`
- `{ type: "done", summary, workflow, session_id, chat_id }`

## Workspace

```
.aiwf/assist/
  index.json
  assist_<uuid>/
    session.json
    context.md
    draft.json
    summary.md
```

## 交互

1. 发送前同步表单 → 只读工作流自动 clone → 解析 `@` 提及
2. ACP 多轮改 `draft.json` → 展示待应用预览
3. 「应用」→ 压栈 → 更新内存
4. 「撤销」→ 恢复上一版内存草稿
5. 工具栏「保存」→ 落盘

## 对话展示规则（v0.3）

工作流助手同时支持**需求探讨**与**编排修改**：

| 场景 | 聊天气泡 | 待应用预览 |
|------|----------|------------|
| 需求探讨 / 问答（未改 draft） | Agent 自然语言回复（可流式） | 无 |
| 编排修改（draft 有结构变更） | 结构 diff（`△` / `+` / `-`） | 结构 changeset |

- Agent 流式输出进入聊天气泡；日志区保留同款文本便于排查。
- 无结构变更时不显示「无结构变更」，而是展示 Agent 的正常回复。

### 附带信息（焦点上下文）

每次发送时，根据意图分级附带上下文给 ACP（用户不可见）：

| 模式 | 触发条件 | 附带内容 |
|------|----------|----------|
| `none` | 探讨 / 问答，无明确编排修改 | 对话模式说明 + 可选当前节点背景 |
| `compact` | 有修改意图 + 仅画布选中节点 | 节点 ID 提示 |
| `full` | 消息含 `@node_id` | 焦点节点完整 JSON + 编辑约束 |

## 与现有能力边界

| 能力 | 职责 |
|------|------|
| 工作流助手 | 编排期 workflow 结构（L1 ACP） |
| 设置 → AI 生成助手 | Role Agent（L0 ACP） |
| 节点 iterate | 运行期 refine 产物（L3 ACP resume） |
