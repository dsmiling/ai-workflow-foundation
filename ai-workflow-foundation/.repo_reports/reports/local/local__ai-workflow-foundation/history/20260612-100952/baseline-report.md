# 仓库分析报告

- 仓库：ai-workflow-foundation
- 根路径：`G:\FF_Wang\ProjectStudy\ai-workflow-foundation\ai-workflow-foundation`

## 项目定位

- 项目摘要：AI Workflow Foundation is a local-first foundation for personal AI workflows。整体属于 Python 应用或服务工程。
- 核心用途：核心特性：Workflow definitions are files.。, 核心特性：Nodes have explicit inputs, outputs, skills, and approval modes.。, 核心特性：Artifacts are written to disk.。, 核心特性：Runs can pause for review.。, 仓库当前暴露出 6 个主要顶层模块，说明它不是单一脚本，而是具备明确分层的工程项目。

## 技术架构

- 架构风格：Python 应用或服务工程
- 运行边界：desktop：承担该层的主要代码与资源组织职责，主要技术为 JSON。, docs：保存项目说明、设计文档和使用指南。，主要技术为 Markdown。, examples：展示项目的用法、演示或样例工程。，主要技术为 JSON、Markdown。, src：承载前端入口、页面编排与交互逻辑。，主要技术为 Python。, tests：汇总测试代码、夹具和验证逻辑。，主要技术为 Python。, web：提供浏览器侧界面、状态和交互能力。，主要技术为 待进一步识别。
- 技术亮点：主要语言：Python、Rust。, 框架线索：Rust crate 布局。, 构建与工具链：cargo。, 质量保障线索：Repository contains visible test/spec-related files。, 关键清单文件：desktop\package-lock.json、desktop\package.json、desktop\src-tauri\Cargo.toml、pyproject.toml。, 已识别入口文件：desktop\node_modules\@tauri-apps\cli\index.js、desktop\node_modules\@tauri-apps\cli\main.js。

## 语义模块

- 语义模块数量：6
- 模块拆解：desktop（目录模块 / 技术：JSON）, docs（文档中心 / 技术：Markdown）, examples（示例集合 / 技术：JSON, Markdown）, src（前端源码 / 技术：Python）, tests（测试集合 / 技术：Python, Repository contains visible test/spec-related files）, web（Web 前端 / 技术：未知）

## 模块分层

- 结构层：展示项目的顶层容器与运行边界，帮助先理解代码库的大框架。；模块：desktop（package-or-app）, docs（文档）, examples（目录模块）, src（源码根）, tests（python-module）, web（frontend）

## 关键链路

- 执行路径：当前关键链路仍以顶层模块协作为主，建议继续结合源码调用图做下一层细化。

## 仓库概览

- 仓库名称：ai-workflow-foundation
- 扫描文件总数：8192
- 检测到的语言：Python, Rust
- 检测到的运行时：Node.js, Python, Rust
- 发现的模块数：6
- 发现的构建步骤数：4

## 模块地图

- 顶层目录：.aiwf, .doctor-workspace, .repo_reports, .test-debug, .test-tmp, .test-workspace, desktop, docs, examples, src, tests, web
- 顶层文件：.gitignore, aiwf_cli.py, Launch-AIWF.ps1, pyproject.toml, README.md
- 关键清单：desktop\package-lock.json, desktop\package.json, desktop\src-tauri\Cargo.toml, pyproject.toml
- 模块候选：desktop (package-or-app), docs (文档), examples (目录模块), src (源码根), tests (python-module), web (frontend)
- 模块关系：未知
- Monorepo 洞察：未知

## 构建与打包

- 包管理器信号：npm, pyproject-based Python packaging, cargo
- 构建工具信号：cargo
- 容器信号：未知
- 清单洞察：desktop\package-lock.json: {, desktop\package.json: 包名：aiwf-desktop, desktop\src-tauri\Cargo.toml: Crate 名称：aiwf-desktop, pyproject.toml: Project name: ai-workflow-foundation
- 构建链：desktop:build => tauri build --no-bundle, desktop:build:installer => tauri build, desktop:dev => tauri dev, desktop:tauri => tauri
- 容器洞察：未知

## 运行时与框架

- 框架线索：Rust crate 布局
- 扩展名分布：.json: 2162, <no_ext>: 1656, .timestamp: 777, .md: 751, .d: 703, .rlib: 656, .rmeta: 655, .o: 532
- 可能的入口文件：desktop\node_modules\@tauri-apps\cli\index.js, desktop\node_modules\@tauri-apps\cli\main.js

## 质量与工程运维

- 质量信号：Repository contains visible test/spec-related files
- CI 相关文件：未知
- 工作流洞察：未知

## 文档与运维

- 文档文件：.aiwf\runs\run_20260610-134037-856535\artifacts\build_plan.md, .aiwf\runs\run_20260610-134037-856535\artifacts\module_breakdown.md, .aiwf\runs\run_20260610-134037-856535\artifacts\requirement_analysis.md, .aiwf\runs\run_20260610-134037-856535\revisions\rev_20260610-134112-090878\artifacts\build_plan.md, .aiwf\runs\run_20260610-134037-856535\revisions\rev_20260610-134112-090878\artifacts\module_breakdown.md, .aiwf\runs\run_20260610-134037-856535\revisions\rev_20260610-134112-090878\artifacts\requirement_analysis.md, .aiwf\runs\run_20260610-135500-549457\artifacts\build_plan.md, .aiwf\runs\run_20260610-135500-549457\artifacts\module_breakdown.md, .aiwf\runs\run_20260610-135500-549457\artifacts\requirement_analysis.md, .aiwf\runs\run_20260610-140006-822624\artifacts\module_breakdown.md, .aiwf\runs\run_20260610-140006-822624\artifacts\requirement_analysis.md, .aiwf\runs\run_20260610-140148-455914\artifacts\module_breakdown.md, .aiwf\runs\run_20260610-140148-455914\artifacts\requirement_analysis.md, .aiwf\runs\run_20260610-142618-210854\artifacts\module_breakdown.md, .aiwf\runs\run_20260610-142618-210854\artifacts\requirement_analysis.md
- 模块文档覆盖率：3/6 个模块包含 Markdown 文档

## 风险与后续方向

- 在 .github workflows 下未检测到可见的 CI 文件。
- 仓库顶层目录较多，可能需要按模块继续深挖。

## 评估摘要

- 项目重量：L3（51/100）
- 项目健康度：88/100
- 最重模块：desktop [M4/75], tests [M3/44], examples [M3/42], src [M3/40], docs [M2/34]
- 扫描了 8192 个文件，覆盖 6 个模块。
- 检测到 2 种语言和 3 类运行时目标。
