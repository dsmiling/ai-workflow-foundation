# 个人 AI 工作流底座需求草案

版本：v0.1  
状态：需求 review 草案  
日期：2026-06-10

## 1. 产品定位

本系统定位为一个面向个人和工程型用户的 AI 工作流底座。

它不是传统工作流平台，不是单一 Agent，也不是低代码自动化工具，而是一个可以让用户定义、理解、调试、审核、重跑和版本化 AI 工作流产出的本地优先系统。

一句话定义：

```text
一个像 Git 一样管理 AI 工作流过程和产出的个人底座。
```

更完整的定义：

```text
个人 AI 工作流底座
= 可视化流程制定器
+ AI 驱动节点
+ Skill 描述挂载
+ Artifact 产物管理
+ Review/审批/回退
+ 对话式节点优化
```

## 2. 目标用户

第一阶段目标用户：

- 系统设计者本人。
- 工程型用户。
- 能理解节点输入、输出、产物和流程状态的人。

暂不优先服务：

- 完全非技术用户。
- 大规模团队协作用户。
- 企业级权限/租户/审计用户。

## 3. 设计原则

核心原则：

```text
本地优先
单人可用
可分发
可视化理解
节点可调试
产物可审核
失败可停住
人工可修改
版本可回退
```

优先级：

```text
可控、可审核、可回退
> 工作流可配置
> 反复对话修改
> 自动化速度
```

使用者必须能理解：

- 每个节点的作用。
- 每个节点的输入来自哪里。
- 每个节点的输出是什么。
- 每个节点的 Skill 描述是什么。
- 当前节点是否需要审批。
- 节点产物为什么通过或失败。
- 某次修改改变了什么。

## 4. 系统边界

### 4.1 系统应该负责

系统负责：

- 定义工作流。
- 配置节点。
- 可视化节点输入、输出、参数和状态。
- 通过 AI/Agent 执行节点。
- 通过 Skill 描述表达节点执行意图。
- 保存每个节点的产物。
- 支持人工审核节点产物。
- 支持自动审批、AI 审批、人工审批。
- 支持节点失败后停住。
- 支持人工编辑 Artifact 后继续。
- 支持基于自然语言反馈修改节点、Skill、参数或产物。
- 将自然语言反馈落成结构化变更。
- 支持节点重跑。
- 支持版本提交。
- 支持产物 diff。
- 支持回滚到历史版本。

### 4.2 系统第一版不负责

第一版暂不负责：

- 多人实时协作。
- 企业级权限系统。
- 租户隔离。
- 云端任务队列。
- 分布式执行。
- 复杂拖拽式低代码平台。
- 完整 Unity 工程自动生成。
- 完整自动测试闭环。
- 完整 BPMN/PI 企业流程管理。
- 内置所有 Agent 框架。
- 内置所有模型供应商。

这些能力可以作为后续扩展，但不进入第一版核心闭环。

## 5. 核心概念

第一版只保留以下核心概念：

```text
Workflow
Node
SkillSpec
Run
Artifact
Review
Revision
Executor
```

### 5.1 Workflow

Workflow 是一个工作流定义。

它描述：

- 有哪些节点。
- 节点之间的顺序或依赖。
- 每个节点的输入。
- 每个节点的输出。
- 每个节点的审批策略。
- 每个节点使用的 Skill 描述。

第一版建议使用 YAML/JSON 持久化，同时在 UI 中可视化编辑。

### 5.2 Node

Node 是工作流的最小执行单元。

节点应该明确：

- 节点做什么。
- 输入是什么。
- 输出是什么。
- 使用哪个 SkillSpec。
- 使用哪个 Executor。
- 是否需要审批。
- 失败后如何处理。

第一版节点类型：

```text
ai       AI 推理节点
skill    Skill 描述执行节点
tool     外部工具或脚本节点
review   人工审核节点
route    条件分支节点
```

### 5.3 SkillSpec

SkillSpec 不是传统插件 SDK。

SkillSpec 是节点的执行描述，重点表达：

- 节点目标。
- 输入上下文。
- 输出要求。
- 质量标准。
- 约束条件。
- 可选参考资料。

SkillSpec 不强制要求用户写代码或固定接口。

示例：

```yaml
id: module_mapping
name: 模块映射
description: 根据需求、Wiki 和模块库生成大活动模块映射。
goal: 输出每个功能需求对应的活动模块、标准库支持情况、缺失项和风险。
output:
  primary: module_mapping.md
  structured: module_mapping.json
quality:
  - 每个模块必须说明用途。
  - 每个模块必须说明输入和输出。
  - 每个模块必须标记是否已有标准库支持。
  - 缺失模块必须列出风险。
```

关键原则：

```text
Skill 可以自由描述执行方式，但 Output Contract 必须明确。
```

### 5.4 Run

Run 是一次工作流运行实例。

每个 Run 应该保存：

- 本次运行使用的 Workflow 快照。
- 当前节点状态。
- 所有节点产物。
- 人工审核记录。
- 对话记录。
- 节点重跑记录。
- Revision 记录。

### 5.5 Artifact

Artifact 是节点产物。

Artifact 可以是：

- Markdown 描述。
- JSON 结构化数据。
- 配置文件。
- 图片。
- Unity Prefab。
- 代码文件。
- Patch。
- 报告。

第一版过程描述以 Markdown 为主，结构化结果使用 JSON，实际业务产物按工作流需求决定。

### 5.6 Review

Review 是人工或 AI 对节点产物的审核记录。

审批模式：

```text
auto   自动通过
ai     AI 审批通过后继续
human  人工审核通过后继续
```

Review 操作：

- approve。
- reject_with_feedback。
- edit_artifact。
- rerun_node。
- update_node_params。
- update_skill_spec。
- commit_revision。
- rollback_revision。

### 5.7 Revision

Revision 是一次稳定产出的版本记录。

它类似 Git commit，但管理的不只是代码，而是：

- Workflow 快照。
- Node 配置。
- Skill 描述。
- Artifact。
- Review 记录。
- 对话反馈。
- 结构化变更。

第一版目标：

- 能提交。
- 能查看 diff。
- 能回滚。

Branch 可以后续再做。

### 5.8 Executor

Executor 是节点执行器。

Executor 可以是：

- LLM。
- Agent。
- AI Harness。
- OpenClaw。
- LangGraph 子图。
- OpenAI Agents SDK。
- 本地脚本。
- MCP 工具。
- 人工审核器。

底座只关心统一协议：

```text
Node Input -> Executor -> Node Output
```

第一版可以先实现一个通用 LLM Executor。

## 6. 核心工作循环

系统的核心体验不是“一键跑完整条流水线”，而是逐个节点调试和固化：

```text
配置节点
-> 执行节点
-> 查看产物
-> 审核产物
-> 对话反馈
-> 结构化修改节点/Skill/参数/产物
-> 重跑节点
-> 满意后提交 Revision
-> 继续后续节点
```

自然语言反馈必须最终落成结构化变更。

示例：

用户反馈：

```text
这个节点拆得太粗，活动奖励部分需要拆成登录奖励、阶段奖励、排行榜奖励。
```

系统应转化为结构化变更：

```json
{
  "target": "node.skill_spec",
  "operation": "update",
  "changes": {
    "quality": [
      "奖励模块必须拆分为登录奖励、阶段奖励、排行榜奖励。",
      "每个奖励模块必须说明触发条件和配置来源。"
    ]
  }
}
```

## 7. 第一版 MVP 范围

第一版目标是跑通通用 AI 工作流底座，而不是完整 Unity 自动化。

MVP 必须包含：

- 可创建 Workflow。
- 可创建 Node。
- 可配置节点 Skill 描述。
- 可视化查看节点输入、输出、参数。
- 可执行 AI 节点。
- 可保存 Markdown Artifact。
- 可保存可选 JSON Artifact。
- 可设置审批模式：auto / ai / human。
- 节点失败后停住。
- 人工可编辑 Artifact。
- 人工可给出 promote/feedback。
- 反馈可转结构化变更。
- 可重跑节点。
- 可提交 Revision。
- 可查看 Artifact diff。
- 可回滚 Revision。

MVP 示例工作流：

```text
需求输入
-> 需求分析节点
-> 模块拆解节点
-> 人工审核节点
-> 生成计划节点
-> commit
-> rollback
```

Unity 大活动创建作为第一个真实服务示例，但不要求第一版完整落地 Unity 工程。

## 8. Unity 大活动示例边界

Unity 示例工作流用于验证底座能力。

建议第一阶段只做：

```text
需求输入
-> 需求解析
-> Unity 工程索引描述
-> 模块库读取
-> 模块映射
-> 人工审核模块映射
-> 生成计划
-> 版本提交
```

第一阶段产物：

- requirement_analysis.md
- module_mapping.md
- module_mapping.json
- build_plan.md
- review_report.md

暂不强制：

- 真实 Unity 代码 patch。
- Prefab 自动生成。
- 动画时序自动调整。
- 音效自动接入。
- UIKey 自动绑定。
- Unity Editor 自动验证。

## 9. 推荐本地目录结构

```text
.aiwf/
  workflows/
    unity_activity_create.yaml
  skills/
    requirement_analysis.yaml
    module_mapping.yaml
  runs/
    run_001/
      workflow.lock.yaml
      state.json
      conversation.md
      artifacts/
      reviews/
      revisions/
  knowledge/
  commits/
```

## 10. 推荐技术路线

第一版建议：

```text
Desktop Shell: Tauri 或 Electron
Web Panel: React
Backend: Python FastAPI
Runner: Python
Storage: SQLite + 文件系统
Workflow Config: YAML/JSON
Artifacts: 文件系统
Revision: 轻量自研 Git-like 语义
Executor: 通用 LLM Executor
```

可后续接入：

- LangGraph：复杂 AI 状态图。
- Temporal：长时可靠执行。
- OpenAI Agents SDK：Agent 执行器。
- AI Harness：节点执行器。
- OpenClaw：节点执行器。
- Camunda/PI：流程模板或审批方法论。

## 11. 操作面板需求

第一版面板应该优先支持理解和调试节点。

建议布局：

```text
左侧：Workflow 节点列表和状态
中间：当前 Node 的输入、Skill 描述、参数
右侧：Artifact 输出、Diff、Review
底部：对话反馈和执行日志
```

每个节点必须展示：

- 节点名称。
- 节点目标。
- 节点类型。
- 输入来源。
- 输出目标。
- Skill 描述。
- 输出契约。
- 审批级别。
- 当前执行状态。
- 当前 Artifact。
- 历史 Revision。
- 最近反馈。

第一版不优先做复杂拖拽画布。

## 12. 需要注意的点

### 12.1 不要把底座做成大平台

风险：

```text
过早引入权限、租户、复杂调度、分布式执行，会导致个人用户无法轻量部署。
```

应对：

```text
第一版坚持本地优先、单人使用、文件可见、SQLite 索引。
```

### 12.2 Skill 不能只有自由文本

风险：

```text
Skill 如果只有自然语言描述，节点输出会不可控。
```

应对：

```text
Skill 可以自由描述执行意图，但必须声明输出契约、产物路径和验收标准。
```

### 12.3 工作流不是一次性流水线

风险：

```text
如果按普通 pipeline 设计，会丢失对话修改、人工审核和节点调试能力。
```

应对：

```text
围绕 Run -> Artifact -> Review -> Feedback -> Structured Change -> Rerun -> Revision 设计。
```

### 12.4 产物必须可见、可编辑、可版本化

风险：

```text
如果产物只存在数据库或对话上下文里，用户无法审查、回滚和复盘。
```

应对：

```text
所有关键产物落盘，Markdown/JSON 优先，复杂产物按文件保存。
```

### 12.5 AI 修改必须结构化

风险：

```text
自然语言反馈如果不落成结构化变更，系统无法稳定重跑和复现。
```

应对：

```text
所有反馈先转成 change request，再应用到 Node/Skill/Artifact/Workflow。
```

### 12.6 审批级别要简单

风险：

```text
审批模型过复杂会拖慢 MVP。
```

应对：

```text
第一版只保留 auto / ai / human。
```

### 12.7 不要先做复杂画布

风险：

```text
拖拽画布会消耗大量前端精力，但不一定提升节点调试质量。
```

应对：

```text
第一版用节点列表 + 详情面板 + Artifact/Diff/Review。
```

### 12.8 不要过早绑定某个 Agent 框架

风险：

```text
绑定 LangGraph、OpenClaw 或 AI Harness 会限制底座通用性。
```

应对：

```text
通过 Executor Adapter 接入外部能力，底座只维护统一输入输出协议。
```

## 13. 待确认问题

以下问题需要继续 review：

1. Workflow 定义是否必须以 YAML 为主，UI 只是 YAML 的可视化编辑器？
2. SkillSpec 是否允许完全无代码，仅由 LLM Executor 执行？
3. 第一版是否需要支持 tool/script 节点，还是只做 AI 节点和 review 节点？
4. Revision 是否第一版就需要真实 Git 后端，还是先做轻量自研版本记录？
5. Artifact diff 第一版只支持文本 diff，还是需要支持图片/二进制产物 diff？
6. AI 审批节点的判断标准从哪里来，是 Skill quality 还是单独 ReviewSpec？
7. 用户反馈转结构化变更时，是否必须先让用户确认 change request？
8. 第一版桌面壳是否必要，还是先用本地 Web 服务即可？
9. 是否需要内置一个 Unity 示例模板，作为默认 demo？
10. 是否需要从第一版开始支持导入/导出 workflow 包？

## 14. 建议的第一阶段验收标准

第一阶段完成时，应该能做到：

1. 用户通过 UI 创建一个简单工作流。
2. 用户创建 3 到 5 个节点。
3. 每个节点可配置 Skill 描述、输入、输出和审批模式。
4. 系统能执行 AI 节点并生成 Markdown Artifact。
5. 用户能查看并编辑 Artifact。
6. 用户能对节点产物进行 approve/reject。
7. reject 后用户能输入反馈。
8. 系统能把反馈转成结构化变更。
9. 用户确认后应用变更并重跑节点。
10. 用户能提交一次 Revision。
11. 用户能查看两次 Revision 的文本 diff。
12. 用户能回滚到历史 Revision。

## 15. 当前结论

当前需求是成立的。

最小可行方向不是构建企业级工作流平台，而是构建：

```text
AI Workflow Git
```

它用极简方式管理：

- 流程。
- 节点。
- Skill 描述。
- 节点产物。
- 人工反馈。
- 审批记录。
- 版本提交。
- 回滚记录。

第一版重点不是自动化深度，而是让用户清楚、可控、可审核、可回退地管理每一个 AI 节点产出。
