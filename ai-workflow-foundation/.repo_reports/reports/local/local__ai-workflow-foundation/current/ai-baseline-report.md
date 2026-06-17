# 仓库分析报告

- 仓库：ai-workflow-foundation
- 分析来源：AI 增强解析

## 项目定位

- 项目摘要：用文件化 workflow、skill、run artifact、review、change request、revision 构成可审阅、可回滚、可重跑的 AI 工作流底座。
- 目标用户：需要本地运行 AI 工作流的个人开发者；想把 AI 任务拆成可审阅节点的工具构建者；准备建设 Wayland 式任务编排工作台的产品研发者
- 适用场景：本地 AI 工作流编排；带人工审批的多步骤 AI 产物生成；工作流模板、技能契约、运行证据的管理；桌面端任务控制台原型

## 技术架构

- 架构风格：Python 本地运行器 + 文件存储 + 原生 HTTP API + 无构建 Web 面板 + Tauri 桌面壳
- 运行边界：CLI 和 Tauri 桌面壳负责启动与入口；HTTP API 暴露 workflow、run、review、artifact、revision、package 操作；WorkflowRunner 负责节点执行、暂停、恢复和重跑；WorkflowStore 负责 .aiwf 下的运行证据、工件、审阅、变更、修订落盘；web/index.html 提供三栏控制台式界面
- 技术亮点：运行证据全部落盘，便于审计和回滚；workflow.lock.json 固化单次运行的工作流快照；review reject 会转为结构化 change request；SkillExecutor 可把外部 SKILL.md 引入节点执行上下文；Tauri 自动启动本地 Python 后端并打开 Web 面板

## 核心模块

- Workflow 数据模型（能力模块）：定义 SkillSpec、NodeSpec、WorkflowSpec、RunState 等核心对象。
- 工作流执行器（能力模块）：按节点顺序执行、解析上游 artifact 输入、处理 review pause、resume、rerun。
- 本地证据存储（能力模块）：管理 .aiwf/runs 下的 state、artifact、review、change、revision 文件。
- Executor 适配层（能力模块）：提供 mock、OpenAI-compatible、skill orchestration 三类执行路径。
- 本地 HTTP API（能力模块）：向前端暴露 workflow CRUD、run、review、change、revision、artifact、package API。
- Web 三栏控制台（能力模块）：提供调度、工作流编辑、Artifact、Review、Changes、Revisions 的单页界面。
- Tauri 桌面壳（能力模块）：解析项目根、启动 Python 后端、选择端口、等待健康检查、提供原生窗口入口。

## 关键链路

- 选择 workflow -> validate -> start run -> runner 逐节点执行 -> artifact 落盘 -> human review 暂停 -> approve/resume 或 reject/change/rerun -> commit revision
- workflow 模板从 examples/workflows 和 .aiwf/workflows 发现，示例只读，工作区副本可编辑
- artifact 可通过 API 和 Web 编辑，编辑后状态消息会标记人工修改
- revision 保存 artifacts/reviews/changes/state/workflow.lock.json，并支持 diff 与 rollback

## 接入判断

- 直接使用：可以作为 AI 工作流底座原型直接运行，但还不能直接等同 Wayland 级产品工作台。
- 工作流适配：与 Wayland 式本地任务编排高度同向，尤其是本地运行、人工审批、可追踪 artifact、可回滚修订这些能力。
- 接入建议：保留 runner/store/api/contracts 作为二次开发基础。；重构前端信息架构，补任务、会话、上下文、配置等产品层。；先把当前三栏控制台升级成左侧页签、中间任务工作区、右侧上下文详情的工作台，而不是先做复杂 DAG 画布。

## 项目价值评估

- 项目归类：本地优先 AI 工作流控制平面原型
- 项目体量：小到中型，可作为产品化底座继续扩展
- 作用面：工作流编排、运行审计、人工审批、产物回滚
- 解决问题：把 AI 任务拆成可追踪节点；把节点产物落盘并纳入审阅；把拒绝反馈转为可应用的变更请求；为本地桌面工作台提供 API 与运行时基础
- 同类方案对比：相比普通聊天工具，它更强调 workflow、artifact、review、revision。；相比完整自动化平台，它更轻量，但缺少队列、并发、权限和插件生态。；相比 Wayland，它已有底层运行证据链，但缺少任务工作台和会话体验。
- 接入成本：中等。后端可沿用，前端和产品对象模型需要系统重构。
- 适合项目：本地 AI 工作台；个人自动化控制台；可审阅 AI 产物流水线；技能/工作流模板管理工具
- 即插即用：原型可运行，不适合不改造就作为正式产品使用。
- 证据强度：较强。README、architecture、runner、storage、server、web、desktop 均有对应证据。
- 投入产出比：建议投入

- 推荐动作：保留当前执行底座，前端从工程控制台改为任务编排工作台。
- 判断依据：当前 runner/store/api 已覆盖本地 AI 工作流最小闭环。；Wayland 式体验缺口主要在产品对象和 UI 信息架构。；先做任务工作台比先做复杂 DAG 画布更贴近用户目标。

## 风险与后续方向

- 当前 runner 是线性节点执行，尚无真正 DAG 调度、并发、依赖图和队列。
- HTTP server 基于标准库手写路由，产品规模扩大后会缺中间件、鉴权、错误规范和流式能力。
- Web UI 是单文件实现，不适合承载 Wayland 级交互复杂度。
- OpenAI executor 只有基础 chat completions 调用，没有工具调用、流式输出、取消、重试、成本统计。
- Skill 仍主要是描述性契约，不是完整插件/工具沙箱。

## 不确定点

- 未检查外部 requirements 文档 ../docs/ai-workflow-foundation-requirements.md，因为它不在当前仓库根的证据范围内。
- 本次重点是功能梳理和 UI 规划，没有运行完整测试或启动桌面应用验证。
