# 仓库索引

- 仓库：ai-workflow-foundation
- 已发现模块：6
- 清单洞察：4
- 构建步骤：4
- 模块关系：0

## 项目定位

- 项目摘要：AI Workflow Foundation is a local-first foundation for personal AI workflows。整体属于 Python 应用或服务工程。
- 架构风格：Python 应用或服务工程
- 核心用途：核心特性：Workflow definitions are files.。；核心特性：Nodes have explicit inputs, outputs, skills, and approval modes.。；核心特性：Artifacts are written to disk.。；核心特性：Runs can pause for review.。
- 关键链路：当前关键链路仍以顶层模块协作为主，建议继续结合源码调用图做下一层细化。

## 语义模块

- desktop：`desktop`（目录模块）
  - 职责：作为 `desktop` 路径下的主模块，承载该层的主要代码与资源。
  - 技术：JSON
- docs：`docs`（文档中心）
  - 职责：保存项目说明、设计文档和使用指南。
  - 技术：Markdown
- examples：`examples`（示例集合）
  - 职责：展示项目的用法、演示或样例工程。
  - 技术：JSON, Markdown
- src：`src`（前端源码）
  - 职责：承载前端入口、页面编排与交互逻辑。
  - 技术：Python
- tests：`tests`（测试集合）
  - 职责：汇总测试代码、夹具和验证逻辑。
  - 技术：Python, Repository contains visible test/spec-related files
- web：`web`（Web 前端）
  - 职责：提供浏览器侧界面、状态和交互能力。
  - 技术：未知

## 模块分层

- 结构层
  - 目的：展示项目的顶层容器与运行边界，帮助先理解代码库的大框架。
  - 包含模块：desktop（package-or-app）；docs（文档）；examples（目录模块）；src（源码根）；tests（python-module）；web（frontend）

## 模块

- desktop：`desktop`（package-or-app）
- docs：`docs`（文档）
- examples：`examples`（目录模块）
- src：`src`（源码根）
- tests：`tests`（python-module）
- web：`web`（frontend）

## 清单洞察

- desktop\package-lock.json [package-lock.json]
  - {
  - "name": "aiwf-desktop",
  - "version": "0.1.0",
- desktop\package.json [package.json]
  - 包名：aiwf-desktop
  - Scripts: build, build:installer, dev, tauri
  - Dependencies: none
- desktop\src-tauri\Cargo.toml [Cargo.toml]
  - Crate 名称：aiwf-desktop
  - Edition: 2021
  - Dependencies: reqwest, serde, serde_json, tauri
- pyproject.toml [pyproject.toml]
  - Project name: ai-workflow-foundation
  - Version: 0.1.0
  - Dependencies: none

## 模块关系

- 未推断出明确的模块关系。

## 构建步骤

- desktop:build：`tauri build --no-bundle`
- desktop:build:installer：`tauri build`
- desktop:dev：`tauri dev`
- desktop:tauri：`tauri`
