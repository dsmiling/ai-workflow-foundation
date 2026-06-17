# AI 增强解析

## 项目定位

- 仓库类型：本地优先的个人 AI 工作流控制平面原型
- 核心用途：用文件化 workflow、skill、run artifact、review、change request、revision 构成可审阅、可回滚、可重跑的 AI 工作流底座。
- 目标用户：需要本地运行 AI 工作流的个人开发者；想把 AI 任务拆成可审阅节点的工具构建者；准备建设 Wayland 式任务编排工作台的产品研发者
- 适用场景：本地 AI 工作流编排；带人工审批的多步骤 AI 产物生成；工作流模板、技能契约、运行证据的管理；桌面端任务控制台原型

## 技术架构

- 架构模式：Python 本地运行器 + 文件存储 + 原生 HTTP API + 无构建 Web 面板 + Tauri 桌面壳
- 运行边界：CLI 和 Tauri 桌面壳负责启动与入口；HTTP API 暴露 workflow、run、review、artifact、revision、package 操作；WorkflowRunner 负责节点执行、暂停、恢复和重跑；WorkflowStore 负责 .aiwf 下的运行证据、工件、审阅、变更、修订落盘；web/index.html 提供三栏控制台式界面
- 关键链路：选择 workflow -> validate -> start run -> runner 逐节点执行 -> artifact 落盘 -> human review 暂停 -> approve/resume 或 reject/change/rerun -> commit revision；workflow 模板从 examples/workflows 和 .aiwf/workflows 发现，示例只读，工作区副本可编辑；artifact 可通过 API 和 Web 编辑，编辑后状态消息会标记人工修改；revision 保存 artifacts/reviews/changes/state/workflow.lock.json，并支持 diff 与 rollback

## 核心模块

- Workflow 数据模型：定义 SkillSpec、NodeSpec、WorkflowSpec、RunState 等核心对象。
- 工作流执行器：按节点顺序执行、解析上游 artifact 输入、处理 review pause、resume、rerun。
- 本地证据存储：管理 .aiwf/runs 下的 state、artifact、review、change、revision 文件。
- Executor 适配层：提供 mock、OpenAI-compatible、skill orchestration 三类执行路径。
- 本地 HTTP API：向前端暴露 workflow CRUD、run、review、change、revision、artifact、package API。
- Web 三栏控制台：提供调度、工作流编辑、Artifact、Review、Changes、Revisions 的单页界面。
- Tauri 桌面壳：解析项目根、启动 Python 后端、选择端口、等待健康检查、提供原生窗口入口。

## 接入判断

- 是否可直接使用：可以作为 AI 工作流底座原型直接运行，但还不能直接等同 Wayland 级产品工作台。
- 工作流适配：与 Wayland 式本地任务编排高度同向，尤其是本地运行、人工审批、可追踪 artifact、可回滚修订这些能力。
- 接入建议：保留 runner/store/api/contracts 作为二次开发基础。；重构前端信息架构，补任务、会话、上下文、配置等产品层。；先把当前三栏控制台升级成左侧页签、中间任务工作区、右侧上下文详情的工作台，而不是先做复杂 DAG 画布。

## 项目价值评估

- 项目归类：本地优先 AI 工作流控制平面原型
- 体量判断：小到中型，可作为产品化底座继续扩展
- 作用面：工作流编排、运行审计、人工审批、产物回滚
- 解决问题：把 AI 任务拆成可追踪节点；把节点产物落盘并纳入审阅；把拒绝反馈转为可应用的变更请求；为本地桌面工作台提供 API 与运行时基础
- 同类方案对比：相比普通聊天工具，它更强调 workflow、artifact、review、revision。；相比完整自动化平台，它更轻量，但缺少队列、并发、权限和插件生态。；相比 Wayland，它已有底层运行证据链，但缺少任务工作台和会话体验。
- 接入成本：中等。后端可沿用，前端和产品对象模型需要系统重构。
- 适配项目：本地 AI 工作台；个人自动化控制台；可审阅 AI 产物流水线；技能/工作流模板管理工具
- 即插即用：原型可运行，不适合不改造就作为正式产品使用。
- 证据强度：较强。README、architecture、runner、storage、server、web、desktop 均有对应证据。
- 投入产出比：建议投入

- 推荐动作：保留当前执行底座，前端从工程控制台改为任务编排工作台。
- 判断依据：当前 runner/store/api 已覆盖本地 AI 工作流最小闭环。；Wayland 式体验缺口主要在产品对象和 UI 信息架构。；先做任务工作台比先做复杂 DAG 画布更贴近用户目标。

## 风险

- 当前 runner 是线性节点执行，尚无真正 DAG 调度、并发、依赖图和队列。
- HTTP server 基于标准库手写路由，产品规模扩大后会缺中间件、鉴权、错误规范和流式能力。
- Web UI 是单文件实现，不适合承载 Wayland 级交互复杂度。
- OpenAI executor 只有基础 chat completions 调用，没有工具调用、流式输出、取消、重试、成本统计。
- Skill 仍主要是描述性契约，不是完整插件/工具沙箱。

## 不确定点

- 未检查外部 requirements 文档 ../docs/ai-workflow-foundation-requirements.md，因为它不在当前仓库根的证据范围内。
- 本次重点是功能梳理和 UI 规划，没有运行完整测试或启动桌面应用验证。

## 结构化详尽解析

# 详尽解析报告

## 仓库速览

- 仓库类型：Python 应用或服务工程
- 仓库用途：AI Workflow Foundation is a local-first foundation for personal AI workflows。整体属于 Python 应用或服务工程。
- 适用场景：Workflow definitions are files.；Nodes have explicit inputs, outputs, skills, and approval modes.；Artifacts are written to disk.；Runs can pause for review.
- 核心技术：Python、Rust、Rust crate 布局、cargo
- 是否值得继续看：建议继续深入

## 使用判断

- 怎么启动：未知
- 怎么构建：desktop:build -> tauri build --no-bundle；desktop:build:installer -> tauri build
- 依赖环境：Node.js 环境；Rust 工具链；cargo 构建工具
- 我能不能直接用：更适合作为参考实现，直接投入生产前仍需补充验证。
- 我能不能接入工作流：更适合作为实现参考，需要结合你的现有工作流做二次判断。

## 模块分层

- 结构层
  - 目的：展示项目的顶层容器与运行边界，帮助先理解代码库的大框架。
  - 包含模块：desktop（package-or-app）；docs（文档）；examples（目录模块）；src（源码根）；tests（python-module）；web（frontend）

## 模块解析

- 模块：desktop
  - 角色：package-or-app
  - 职责：这是一个顶层结构模块，用于承载该层代码与资源。
  - 技术：<no_ext>、.json、.timestamp、.d
  - 关键文件：desktop\node_modules\@tauri-apps\cli\index.js、desktop\node_modules\@tauri-apps\cli\main.js、desktop\node_modules\@tauri-apps\cli-win32-x64-msvc\package.json、desktop\node_modules\@tauri-apps\cli\package.json、desktop\package.json
  - 是否核心：否
- 模块：docs
  - 角色：文档
  - 职责：这是一个顶层结构模块，用于承载该层代码与资源。
  - 技术：.md
  - 关键文件：未知
  - 是否核心：否
- 模块：examples
  - 角色：目录模块
  - 职责：这是一个顶层结构模块，用于承载该层代码与资源。
  - 技术：.json、.md
  - 关键文件：未知
  - 是否核心：否
- 模块：src
  - 角色：源码根
  - 职责：这是一个顶层结构模块，用于承载该层代码与资源。
  - 技术：.py
  - 关键文件：未知
  - 是否核心：是
- 模块：tests
  - 角色：python-module
  - 职责：这是一个顶层结构模块，用于承载该层代码与资源。
  - 技术：.py
  - 关键文件：未知
  - 是否核心：否
- 模块：web
  - 角色：frontend
  - 职责：这是一个顶层结构模块，用于承载该层代码与资源。
  - 技术：.html
  - 关键文件：未知
  - 是否核心：否

## 接入建议

- 接入前先跑通 dev/build/test 三条主命令，再决定是直接使用还是参考实现。

## 文档产出

- 项目说明：项目用途说明；技术架构摘要；运行与构建说明
- 模块说明：desktop 模块说明；docs 模块说明；examples 模块说明；src 模块说明；tests 模块说明
- 接入说明：接入判断说明；工作流适配建议；风险与限制说明

## 补充判断

- 文档完备度：较高
- 接入友好度：中
- 工作流适配度：中
- 工程复杂度：中高
